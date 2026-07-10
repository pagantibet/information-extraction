"""
Tibetan Title Extraction

Description
-----------------
This script extracts title-tagged lines from TEI XML files - developed specifically for use with Transkribus 'structure' tags e.g. <ab facs="###" type="Title">.
# --- todo - add more data on export options selected from Transkribus e.g. <lb> and zones

For each title found, outputs:
  - batch_name        : from <titleStmt><title type="main">
  - title_text        : the transcribed title line (multiple lines joined with ' | ')
  - title_line_count  : number of manuscript lines merged into this title
  - image_name        : name of the image from <graphic url="..."> in the facsimile section
  - page_n            : page number (<pb n="...">)
  - pb_since_last     : number of <pb> breaks since the previous title (proxy for how many pages in each text)
  - context_before    : N lines of text preceding the title (default 3); ||| separated for Tibetan (Unicode)
  - context_after     : N lines of text following the title (default 3); ||| separated for Tibetan (Unicode)

Multi-line title merging
------------------------
Titles are sometimes split across two or more consecutive <lb> lines that are all tagged subtype="Title" AND share the same parent TextRegion in the facsimile. When this happens the lines are merged into one
output row, joined with ' | ' so the individual lines remain distinguishable.

Three cases are handled:
  Case 1: one Title line per TextRegion → one output row
  Case 2: multiple Title lines in the same TextRegion → merged into one row
  Case 3: Title TextRegion where some child lines are untagged (e.g. batch letter/number on the cover page or the title is above the main body of text) → only the Title-tagged children are extracted, the rest is ignored.

Requirements
------------------------
 - Python 3.9+
 - lxml >= 4.9 
 
 Install lxml:
    pip install -r requirements.txt 
    
    or 

    pip install "lxml>=4.9"

To Use
------------------------
    python Tibetan_titles_extract.py input.xml [--context 3] [--output results.csv]

To process multiple files:
    python Tibetan_titles_extract.py *.xml --output results.csv

Notes
------------------------
This script assumes a specific Transkribus export configuration (structure tags, <lb> line export, and zone/region export all enabled, with subtype="Title" applied to title lines).
A mismatched export configuration will not raise an error - it will likely produce zero (or incomplete) titles.
"""

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path
from lxml import etree

TEI_NS = 'http://www.tei-c.org/ns/1.0'
XML_NS = 'http://www.w3.org/XML/1998/namespace'

# Separator used when joining multi-line titles into a single string
MULTILINE_SEP = ' | '


def get_text_from_lb(lb: etree._Element) -> str:
    """
    Collect the text content of a line starting at an <lb> element.
    Stops at the next <lb> or <pb>.
    Includes text inside inline elements (add, hi, etc.) and their tails.
    """
    parent = lb.getparent()
    if parent is None:
        return lb.tail.strip() if lb.tail else ''

    children = list(parent)
    try:
        idx = children.index(lb)
    except ValueError:
        return ''

    parts = []
    if lb.tail:
        parts.append(lb.tail)

    for sib in children[idx + 1:]:
        local = etree.QName(sib.tag).localname if '{' in sib.tag else sib.tag
        if local in ('lb', 'pb'):
            break
        # Include text inside inline elements (add, hi, del, etc.)
        for node in sib.iter():
            if node.text:
                parts.append(node.text)
            if node is not sib and node.tail:
                parts.append(node.tail)
        if sib.tail:
            parts.append(sib.tail)

    return ''.join(parts).strip()


def build_zone_map(tree: etree._ElementTree) -> dict:
    """
    Return {zone_xml_id: subtype} for all <zone> elements.
    """
    zone_map = {}
    for zone in tree.findall(f'.//{{{TEI_NS}}}zone'):
        zid = zone.get(f'{{{XML_NS}}}id')
        subtype = zone.get('subtype')
        if zid:
            zone_map[zid] = subtype
    return zone_map


def build_image_map(tree: etree._ElementTree) -> dict:
    """
    Return {surface_xml_id: image_filename} by reading <graphic url="..."> inside each <surface> in the facsimile section.
    """
    image_map = {}
    for facsimile in tree.findall(f'.//{{{TEI_NS}}}facsimile'):
        facs_id = facsimile.get(f'{{{XML_NS}}}id')
        graphic = facsimile.find(f'.//{{{TEI_NS}}}graphic')
        if facs_id and graphic is not None:
            image_map[facs_id] = graphic.get('url', '')
    return image_map


def build_title_group_map(tree: etree._ElementTree, zone_map: dict) -> dict:
    """
    Identify Title line zones that share a parent TextRegion and should be merged into a single output row.

    Returns a dict mapping each Title line zone id to a group key: {zone_id: group_key}

    For Case 1, the group key is the zone_id itself — no merging happens.

    For Case 2, all lines in that region share the parent region's xml:id as their group key, so they will be collected as one merged row.

    Only zones explicitly tagged subtype="Title" are included. Untagged sibling lines within a Title TextRegion (Case 3) are excluded.
    """
    # Map parent_region_id → [child Title line zone ids]
    region_to_title_lines = defaultdict(list)

    for zone in tree.findall(f'.//{{{TEI_NS}}}zone'):
        zid = zone.get(f'{{{XML_NS}}}id')
        subtype = zone.get('subtype')
        rendition = zone.get('rendition', '')

        if subtype != 'Title' or 'Line' not in rendition:
            continue

        parent = zone.getparent()
        if parent is None:
            region_to_title_lines[zid].append(zid)
            continue

        parent_id = parent.get(f'{{{XML_NS}}}id', '')
        parent_rendition = parent.get('rendition', '')

        if 'TextRegion' in parent_rendition:
            # Group under parent region id
            region_to_title_lines[parent_id].append(zid)
        else:
            # No TextRegion parent — treat as standalone
            region_to_title_lines[zid].append(zid)

    # Invert: zone_id → group_key
    # Group key is the parent region id when multiple Title lines share one,
    # otherwise the zone's own id.
    zone_to_group = {}
    for region_id, line_ids in region_to_title_lines.items():
        if len(line_ids) == 1:
            # Single line — group key is the line's own id (i.e. no merging)
            zone_to_group[line_ids[0]] = line_ids[0]
        else:
            # Multiple Title lines share this region — group under region id
            for lid in line_ids:
                zone_to_group[lid] = region_id

    return zone_to_group


def process_file(xml_path: Path, context_lines: int = 3) -> list[dict]:
    """
    Parse one TEI XML file and return a list of title records.
    Multi-line titles are merged into a single row.
    """
    try:
        relaxed_parser = etree.XMLParser(recover=True, encoding='utf-8')
        tree = etree.parse(str(xml_path), parser=relaxed_parser)

    except etree.XMLSyntaxError as e:
        print(f"  WARNING: XML parse error in {xml_path.name}: {e}",
              file=sys.stderr)
        return []

    ns = {'tei': TEI_NS}

    # --- Batch name ---
    title_elem = tree.find('.//tei:titleStmt/tei:title[@type="main"]', ns)
    batch_name = (title_elem.text.strip()
                  if title_elem is not None and title_elem.text
                  else xml_path.stem)

    # --- Zone + Image map ---
    zone_map  = build_zone_map(tree)
    image_map = build_image_map(tree)

    # --- Multi-line grouping map ---
    # zone_to_group: {Title_line_zone_id → group_key}
    # Lines sharing a group_key will be merged into one output row.
    zone_to_group = build_title_group_map(tree, zone_map)

    # --- Walk body, collecting lbs in document order ---
    body = tree.find('.//tei:body', ns)
    if body is None:
        print(f"  WARNING: No <body> found in {xml_path.name}",
              file=sys.stderr)
        return []

    # Collect all lb and pb elements in document order with their metadata
    elements = []  # list of ('lb'|'pb', element)
    for elem in body.iter():
        local = etree.QName(elem.tag).localname if '{' in elem.tag else elem.tag
        if local in ('lb', 'pb'):
            elements.append((local, elem))

    # Separate lb-only list for context window indexing
    lb_elements = [(i, e) for i, (t, e) in enumerate(elements) if t == 'lb']

    # Track pb counter, page number, and image name per lb position
    pb_at_lb     = {}
    page_n_at_lb = {}
    image_at_lb  = {}

    running_pb    = 0
    running_page_n = '0'
    running_image  = ''

    lb_pos = 0
    for (etype, elem) in elements:
        if etype == 'pb':
            running_pb    += 1
            running_page_n = elem.get('n', str(running_pb))
            pb_facs_ref    = elem.get('facs', '').replace('#', '')
            running_image  = image_map.get(pb_facs_ref, '')
        else:
            pb_at_lb[lb_pos]     = running_pb
            page_n_at_lb[lb_pos] = running_page_n
            image_at_lb[lb_pos]  = running_image
            lb_pos += 1

    # -------------------------------------------------------------------
    # Extract titles, merging multi-line groups
    # -------------------------------------------------------------------
    # Accumulate lines into groups when going through lb_elements in order.
    # When moving to a new group (or hit a non-title line), flush the current group as one output record.

    records        = []
    last_title_pb  = 0

    # Current group accumulator
    current_group_key   = None
    current_group_lines = []   # list of (lb_pos, lb_element)

    def flush_group(group_lines, last_pb):
        """
        Emit one output record for a completed group of Title lines.
        Returns the updated last_title_pb value.
        """
        if not group_lines:
            return last_pb

        # Use the FIRST line's position for page/image metadata
        first_pos  = group_lines[0][0]
        last_pos   = group_lines[-1][0]

        page_n     = page_n_at_lb.get(first_pos, '?')
        image_name = image_at_lb.get(first_pos, '')
        pb_count   = pb_at_lb.get(first_pos, 0)
        pb_since   = pb_count - last_pb

        # Merge text from all lines in the group
        line_texts = [get_text_from_lb(lb) for _, lb in group_lines]
        line_texts = [t for t in line_texts if t]  # drop empty lines
        merged_text = MULTILINE_SEP.join(line_texts)

        # Context: N lines BEFORE the first title line in the group
        before_texts = []
        for j in range(max(0, first_pos - context_lines), first_pos):
            t = get_text_from_lb(lb_elements[j][1])
            if t:
                before_texts.append(t)

        # Context: N lines AFTER the last title line in the group
        after_texts = []
        for j in range(last_pos + 1,
                       min(len(lb_elements), last_pos + context_lines + 1)):
            t = get_text_from_lb(lb_elements[j][1])
            if t:
                after_texts.append(t)

        records.append({
            'batch_name':        batch_name,
            'page_n':            page_n,
            'image_name':        image_name,
            'pb_since_last_title': pb_since,
            'title_line_count':  len(group_lines),
            'title_text':        merged_text,
            'context_before':    ' ||| '.join(before_texts),
            'context_after':     ' ||| '.join(after_texts),
        })

        return pb_count   # new last_title_pb

    for lb_pos, (_, lb) in enumerate(lb_elements):
        facs_ref = lb.get('facs', '').replace('#', '')
        subtype  = zone_map.get(facs_ref)

        if subtype != 'Title':
            # Non-title line — flush any open group
            if current_group_lines:
                last_title_pb = flush_group(current_group_lines, last_title_pb)
                current_group_lines = []
                current_group_key   = None
            continue

        # This line IS a title — find its group key
        group_key = zone_to_group.get(facs_ref, facs_ref)

        if group_key == current_group_key:
            # Same group as the previous title line — accumulate
            current_group_lines.append((lb_pos, lb))
        else:
            # New group — flush the previous one first
            if current_group_lines:
                last_title_pb = flush_group(current_group_lines, last_title_pb)
            current_group_key   = group_key
            current_group_lines = [(lb_pos, lb)]

    # Flush any group still open at the end of the document
    if current_group_lines:
        flush_group(current_group_lines, last_title_pb)

    return records


def main():
    parser = argparse.ArgumentParser(
        description='Extract titles from Transkribus TEI XML')
    parser.add_argument('files', nargs='+', help='TEI XML file(s) to process')
    parser.add_argument('--context', type=int, default=3,
                        help='Number of context lines before/after title (default: 3)')
    parser.add_argument('--output', default='titles_extracted.csv',
                        help='Output CSV file (default: titles_extracted.csv)')
    args = parser.parse_args()

    fieldnames = [
        'batch_name', 'page_n', 'image_name', 'pb_since_last_title',
        'title_line_count', 'title_text', 'context_before', 'context_after'
    ]

    all_records = []
    for pattern in args.files:
        for fpath in (Path('.').glob(pattern)
                      if '*' in pattern else [Path(pattern)]):
            if not fpath.exists():
                print(f"WARNING: File not found: {fpath}", file=sys.stderr)
                continue
            print(f"Processing: {fpath.name}")
            records = process_file(fpath, context_lines=args.context)
            merged = sum(1 for r in records if r['title_line_count'] > 1)
            print(f"  → {len(records)} titles found"
                  + (f" ({merged} multi-line)" if merged else ""))
            all_records.extend(records)

    if not all_records:
        print("No titles found across all files.", file=sys.stderr)
        sys.exit(1)

    out_path = Path(args.output)
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_records)

    print(f"\nDone. {len(all_records)} titles written to {out_path}")


if __name__ == '__main__':
    main()
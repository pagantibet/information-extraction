# Tibetan Title Extraction

A Python script for extracting title-tagged lines from TEI XML files - developed specifically for use with Transkribus 'structure' tags (e.g. `<ab facs="###" type="Title">`). Multi-line titles are merged into a single row, and surrounding text is included in separate columns as context.

This script was developed as part of [PaganTibet](https://www.pagantibet.com/)'s information extraction workflow. 

## Requirements
 
- Python 3.9+
- `lxml >= 4.9`

## Setup
 
```bash
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```
 
## Usage
 
```bash
# Single file
python Tibetan_titles_extract.py input.xml --context 3 --output results.csv
 
# Multiple files
python Tibetan_titles_extract.py *.xml --output results.csv
 
# Print Python, lxml and libxml2 versions
python Tibetan_titles_extract.py --version
```

## Output columns
 
| Column | Description |
|---|---|
| `batch_name` | From `<titleStmt><title type="main">` |
| `page_n` | Page number (`<pb n="...">`) |
| `image_name` | Image filename from `<graphic url="...">` |
| `pb_since_last_title` | `<pb>` breaks since the previous title (proxy for pages per text) |
| `title_line_count` | Number of manuscript lines merged into this title |
| `title_text` | Transcribed title text, multi-line titles joined with ` \| ` |
| `context_before` | N lines preceding the title, `\|\|\|`-separated |
| `context_after` | N lines following the title, `\|\|\|`-separated |

## Expected input
 
A title is identified by `subtype="Title"` on a `Line` zone in the facsimile section, which is linked to the text through `<lb facs="#...">`. A simplified example of a Transkribus export containing a title:
 
```xml
<facsimile xml:id="facs_16">
  <surface>
    <graphic url="IMG_0016.JPG"/>
    <zone rendition="TextRegion" xml:id="facs_16_tr_2" subtype="Title">
      <zone rendition="Line" xml:id="facs_16_tr_2_tl_1" subtype="Title"/>
    </zone>
  </surface>
</facsimile>
...
<pb facs="#facs_16" n="16" xml:id="img_0016"/>
<ab facs="#facs_16_tr_2" type="Title">
  <lb facs="#facs_16_tr_2_tl_1" n="N001"/>(title text)
</ab>
```

## Notes
 
- **Parser tolerance:** the script parses with `recover=True`, which tolerates broken/non-well-formed XML. Recovery behaviour comes from libxml2 (via lxml) and can vary slightly across libxml2 versions. 
Run `python extract_titles.py --version` to record the exact Python/lxml/libxml2 versions used for a given extraction run.
- **Transkribus export settings:** this script assumes structure tags, `<lb>` line export, and zone/region export were all enabled at export, with `subtype="Title"` applied to title lines. A mismatched export configuration won't raise an error but will likely produce zero or incomplete results. Check the output count against the number of titles you expect to confirm.
- **Other Transkribus export options** - beyond those listed - have not been tested.
- **Multi-line title merging:** assumes consecutive Title-tagged lines in the same `TextRegion` are merged into one row, joined with ` | `. Titles split across *separate* regions are not merged, but output as separate entries.
- **XML comments:** a file containing XML comments (`<!-- ... -->`) inside `<body>` will stop with a `TypeError`; remove comments before running.

## License

This project is licensed under the MIT License - see the [LICENSE](https://github.com/pagantibet/normalisation/blob/main/LICENSE) file for details.

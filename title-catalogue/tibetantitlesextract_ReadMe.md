# Tibetan Title Extraction

A Python script for extracting title-tagged lines from TEI XML files - developed specifically for use with Transkribus 'structure' tags e.g. (e.g. `<ab facs="###" type="Title">`).

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
python extract_titles.py input.xml --context 3 --output results.csv
 
# Multiple files (shell-expanded glob)
python extract_titles.py *.xml --output results.csv
 
# Check environment/version info
python extract_titles.py --version
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

## Notes
 
- **Parser tolerance:** the script parses with `recover=True`, which tolerates malformed/non-well-formed XML — common in Transkribus exports. Recovery behaviour comes from libxml2 (via lxml) and can vary slightly across libxml2 versions. 
Run `python extract_titles.py --version` to record the exact Python/lxml/libxml2 versions used for a given extraction run.
- **Transkribus export settings:** this script assumes structure tags, `<lb>` line export, and zone/region export were all enabled at export, with `subtype="Title"` applied to title lines. A mismatched export configuration won't raise an error — it will
  likely produce zero or incomplete titles.
- **Other Transkribus export options** - beyond those listed - are not yet accounted for.
- **Multi-line title merging assumes** consecutive Title-tagged lines share a parent `TextRegion`; any titles split across multiple *separate* regions will not be merged.

## License

This project is licensed under the MIT License - see the [LICENSE](https://github.com/pagantibet/normalisation/blob/main/LICENSE) file for details.

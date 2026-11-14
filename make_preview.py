"""Make a single-file preview of Fred with an edition baked in.

    python scripts/make_preview.py site/data.json preview.html
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

data = json.loads(Path(sys.argv[1]).read_text())
page = (ROOT / "site" / "index.html").read_text()
icon = (ROOT / "site" / "icon.svg").read_text()

inline = "<script>window.FRED_DATA = " + json.dumps(data, ensure_ascii=False).replace("</", "<\\/") + ";</script>\n"
page = page.replace("<script>\n(function", inline + "<script>\n(function", 1)
# A preview is one file: drop links to sibling files.
page = page.replace('<link rel="manifest" href="manifest.webmanifest">\n', "")
data_icon = "data:image/svg+xml," + icon.strip().replace('"', "'").replace("#", "%23")
page = page.replace('href="icon.svg"', f'href="{data_icon}"')
Path(sys.argv[2]).write_text(page)
print(f"wrote {sys.argv[2]}")

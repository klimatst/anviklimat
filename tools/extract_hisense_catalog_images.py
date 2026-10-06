#!/usr/bin/env python3
"""Extract all embedded images from a Hisense XLSX into the GitHub catalog folder."""

from pathlib import Path
import sys
import zipfile
import json

OUT = Path("theme/assets/catalog/hisense/xlsx")

def extract(source):
  OUT.mkdir(parents=True, exist_ok=True)
  rows = []
  with zipfile.ZipFile(source) as z:
    for media in sorted(n for n in z.namelist() if n.startswith("xl/media/")):
      name = Path(media).name
      data = z.read(media)
      (OUT / name).write_bytes(data)
      rows.append({
        "source_media": name,
        "github_path": f"theme/assets/catalog/hisense/xlsx/{name}",
        "size_bytes": len(data),
      })
  (OUT / "image_manifest.json").write_text(
    json.dumps(
      {"source_workbook": Path(source).name, "image_count": len(rows), "images": rows},
      ensure_ascii=False, indent=2
    ),
    encoding="utf-8"
  )
  print(f"Extracted {len(rows)} images")

if __name__ == "__main__":
  if len(sys.argv) != 2:
    raise SystemExit("Usage: python tools/extract_hisense_catalog_images.py <xlsx>")
  extract(sys.argv[1])

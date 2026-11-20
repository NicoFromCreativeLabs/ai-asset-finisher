"""python build_zip.py  ->  dist/ai_asset_finisher.zip (install via Blender > Preferences > Add-ons > Install from Disk)"""
import os
import re
import zipfile

here = os.path.dirname(os.path.abspath(__file__))
pkg = os.path.join(here, "ai_asset_finisher")
ver = re.search(r'"version": \((\d+), (\d+), (\d+)\)', open(os.path.join(pkg, "__init__.py")).read()).groups()
os.makedirs(os.path.join(here, "dist"), exist_ok=True)
out = os.path.join(here, "dist", "ai_asset_finisher.zip")
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk(pkg):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if f.endswith(".pyc"):
                continue
            full = os.path.join(root, f)
            z.write(full, os.path.relpath(full, here))
print("built", out, "v" + ".".join(ver))

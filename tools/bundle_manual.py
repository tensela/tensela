"""Copies the manual of each language (the one-file HTML that the site builds, with its pictures inside) into the
app, so Help → Manual opens without internet: `src/tensela/help/tensela-manual-{en,es}.html`. They are built files,
not kept in the repository; the AppImage is made after running this.

    .venv/bin/python tools/bundle_manual.py [path/to/tensela-site]
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "tensela-site"


def main() -> int:
    target = ROOT / "src" / "tensela" / "help"
    target.mkdir(parents=True, exist_ok=True)
    sources = sorted((SITE / "dist" / "downloads").glob("tensela-manual-*.html"))   # every language the site has
    if not sources:
        print(f"✗ no manual in {SITE / 'dist' / 'downloads'}: build the site first (npm run build).")
        return 1
    for old in target.glob("tensela-manual-*.html"):           # a language the site no longer has, out
        if old.name not in {s.name for s in sources}:
            old.unlink()
    for source in sources:
        shutil.copy2(source, target / source.name)
        print(f"✓ {target / source.name} ({source.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

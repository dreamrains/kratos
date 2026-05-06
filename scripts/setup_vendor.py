"""Download vendor JS files required by the web UI."""

import urllib.request
import sys
from pathlib import Path

VENDOR_DIR = Path(__file__).resolve().parent.parent / "src" / "data_agent" / "web" / "static" / "js"

FILES = {
    "plotly-3.5.0.min.js": "https://cdn.plot.ly/plotly-3.5.0.min.js",
}


def main():
    VENDOR_DIR.mkdir(parents=True, exist_ok=True)

    for filename, url in FILES.items():
        target = VENDOR_DIR / filename
        if target.exists():
            size = target.stat().st_size
            if size > 1_000_000:
                print(f"  [skip] {filename} ({size:,} bytes)")
                continue
            else:
                print(f"  [warn] {filename} exists but only {size:,} bytes, re-downloading...")

        print(f"  [download] {url}")
        try:
            urllib.request.urlretrieve(url, str(target))
            size = target.stat().st_size
            print(f"  [done] {filename} ({size:,} bytes)")
        except Exception as e:
            print(f"  [error] Failed to download {filename}: {e}", file=sys.stderr)
            sys.exit(1)

    print("All vendor files ready.")


if __name__ == "__main__":
    main()

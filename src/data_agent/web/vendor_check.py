"""Check and download vendor JS files on first run."""

from pathlib import Path

VENDOR_DIR = Path(__file__).resolve().parent / "static" / "js"

REQUIRED = {
    "plotly-3.5.0.min.js": "https://cdn.plot.ly/plotly-3.5.0.min.js",
}


def ensure_vendor_files():
    """Download missing vendor files. Called at web server startup."""
    VENDOR_DIR.mkdir(parents=True, exist_ok=True)

    for filename, url in REQUIRED.items():
        target = VENDOR_DIR / filename
        if target.exists() and target.stat().st_size > 1_000_000:
            continue

        import urllib.request
        try:
            print(f"[vendor] Downloading {filename}...")
            urllib.request.urlretrieve(url, str(target))
            print(f"[vendor] {filename} ready ({target.stat().st_size:,} bytes)")
        except Exception as e:
            print(f"[vendor] Warning: failed to download {filename}: {e}")
            print(f"[vendor] Charts will use CDN fallback.")

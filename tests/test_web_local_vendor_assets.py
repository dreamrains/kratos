from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_TEMPLATE = ROOT / "src/data_agent/web/templates/base.html"
STATIC_ROOT = ROOT / "src/data_agent/web/static"


def _base_html() -> str:
    return BASE_TEMPLATE.read_text(encoding="utf-8")


def test_base_template_uses_local_vendor_assets_only() -> None:
    html = _base_html()

    assert "https://cdn.tailwindcss.com" not in html
    assert "https://unpkg.com" not in html
    assert "https://cdn.jsdelivr.net" not in html
    assert "https://fonts.googleapis.com" not in html
    assert "https://fonts.gstatic.com" not in html

    for asset in (
        "vendor/tailwindcss/tailwind-play-cdn.js",
        "vendor/htmx/htmx-1.9.12.min.js",
        "vendor/alpinejs/alpinejs-3.14.8.min.js",
        "vendor/marked/marked-15.0.4.min.js",
        "vendor/katex/katex-0.16.11.min.css",
        "vendor/katex/katex-0.16.11.min.js",
        "vendor/mermaid/mermaid-11.min.js",
        "vendor/highlight/github-dark-11.min.css",
        "vendor/highlight/highlight-11.min.js",
    ):
        assert asset in html


def test_local_vendor_assets_exist() -> None:
    for asset in (
        "vendor/tailwindcss/tailwind-play-cdn.js",
        "vendor/htmx/htmx-1.9.12.min.js",
        "vendor/alpinejs/alpinejs-3.14.8.min.js",
        "vendor/marked/marked-15.0.4.min.js",
        "vendor/katex/katex-0.16.11.min.css",
        "vendor/katex/katex-0.16.11.min.js",
        "vendor/mermaid/mermaid-11.min.js",
        "vendor/highlight/github-dark-11.min.css",
        "vendor/highlight/highlight-11.min.js",
    ):
        path = STATIC_ROOT / asset
        assert path.is_file(), f"Missing local vendor asset: {asset}"
        assert path.stat().st_size > 0

"""Page routes — full HTML rendering via Jinja2 templates."""

from flask import Blueprint, render_template

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/")
def index():
    return render_template("index.html")


@pages_bp.route("/v2-canary")
def v2_canary():
    """Isolated Slice 1 browser canary; not the legacy chat runtime."""
    return render_template("v2_canary.html")

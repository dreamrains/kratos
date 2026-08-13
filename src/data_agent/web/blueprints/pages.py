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


@pages_bp.route("/v2-factor-canary")
def v2_factor_canary():
    """Isolated Slice 2 factor-relationship browser canary."""
    return render_template("v2_factor_canary.html")


@pages_bp.route("/v2-transform-canary")
def v2_transform_canary():
    """Isolated Slice 3 date-transformation browser canary."""
    return render_template("v2_transform_canary.html")


@pages_bp.route("/v2-group-canary")
def v2_group_canary():
    """Isolated Slice 4A group-comparison browser canary."""
    return render_template("v2_group_canary.html")


@pages_bp.route("/v2-time-canary")
def v2_time_canary():
    """Isolated Slice 4B historical-trend browser canary."""
    return render_template("v2_time_canary.html")


@pages_bp.route("/v2-forecast-canary")
def v2_forecast_canary():
    """Isolated Slice 4C backtested-forecast browser canary."""
    return render_template("v2_forecast_canary.html")

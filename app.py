import io
import os
import logging
from pathlib import Path

from flask import Flask, request, Response, jsonify
from kerykeion import AstrologicalSubjectFactory
from kerykeion.chart_data_factory import ChartDataFactory
from kerykeion.charts.chart_drawer import ChartDrawer

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# GeoNames username – set as an environment variable on Render for safety,
# but fall back to the hard-coded value if you prefer.
GEONAMES_USERNAME = os.environ.get("GEONAMES_USERNAME", "siriusrising")


# ── / ──────────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return "Kerykeion API is running"


# ── /test ───────────────────────────────────────────────────────────────────────
# Known-good diagnostic endpoint.  DO NOT MODIFY.
@app.route("/test")
def test():
    """Hard-coded chart for 20 Jan 1957 09:00 GMT, Lennoxtown, Scotland."""
    subject = AstrologicalSubjectFactory.from_birth_data(
        name="Test Subject",
        year=1957,
        month=1,
        day=20,
        hour=9,
        minute=0,
        lng=-4.1974,   # Lennoxtown, Scotland
        lat=55.9742,
        tz_str="Europe/London",
        online=False,
    )
    chart_data = ChartDataFactory.create_natal_chart_data(subject)
    drawer = ChartDrawer(chart_data=chart_data)
    svg_string = drawer.generate_svg_string()
    return Response(svg_string, mimetype="image/svg+xml")


# ── /chart ──────────────────────────────────────────────────────────────────────
@app.route("/chart")
def chart():
    """
    Generate a natal chart SVG from birth data supplied as query parameters.

    Required parameters
    -------------------
    year    : int   e.g. 1990
    month   : int   e.g. 6
    day     : int   e.g=15
    hour    : int   e.g. 14   (24-hour clock, local birth time)
    minute  : int   e.g. 30
    city    : str   e.g. London
    country : str   ISO 3166-1 alpha-2 code, e.g. GB

    Optional parameters
    -------------------
    name    : str   Defaults to "Chart"

    Example
    -------
    /chart?year=1957&month=1&day=20&hour=9&minute=0&city=Lennoxtown&country=GB
    """
    # ── Parse & validate parameters ────────────────────────────────────────────
    errors = []

    def get_int(param):
        raw = request.args.get(param)
        if raw is None:
            errors.append(f"Missing required parameter: {param}")
            return None
        try:
            return int(raw)
        except ValueError:
            errors.append(f"Parameter '{param}' must be an integer, got: {raw!r}")
            return None

    year   = get_int("year")
    month  = get_int("month")
    day    = get_int("day")
    hour   = get_int("hour")
    minute = get_int("minute")

    city    = request.args.get("city",    "").strip()
    country = request.args.get("country", "").strip()
    name    = request.args.get("name",    "Chart").strip()

    if not city:
        errors.append("Missing required parameter: city")
    if not country:
        errors.append("Missing required parameter: country")

    if errors:
        return jsonify({"error": "Invalid parameters", "details": errors}), 400

    # ── Build the astrological subject via GeoNames online lookup ──────────────
    try:
        logger.info(
            "Generating chart for %s – %04d-%02d-%02d %02d:%02d  %s, %s",
            name, year, month, day, hour, minute, city, country,
        )

        subject = AstrologicalSubjectFactory.from_birth_data(
            name=name,
            year=year,
            month=month,
            day=day,
            hour=hour,
            minute=minute,
            city=city,
            nation=country,                     # Kerykeion uses 'nation'
            geonames_username=GEONAMES_USERNAME,
            online=True,                        # Trigger GeoNames lookup
        )

    except Exception as exc:
        logger.exception("GeoNames / subject creation failed")
        return jsonify({
            "error": "Could not resolve location or create astrological subject.",
            "detail": str(exc),
        }), 500

    # ── Calculate chart data & render SVG ──────────────────────────────────────
    try:
        chart_data = ChartDataFactory.create_natal_chart_data(subject)
        drawer = ChartDrawer(chart_data=chart_data)
        svg_string = drawer.generate_svg_string()

    except Exception as exc:
        logger.exception("Chart generation failed")
        return jsonify({
            "error": "Chart generation failed.",
            "detail": str(exc),
        }), 500

    # ── Return the SVG directly ────────────────────────────────────────────────
    return Response(svg_string, mimetype="image/svg+xml")


# ── Entry point (local dev only – Render uses Gunicorn) ────────────────────────
if __name__ == "__main__":
    app.run(debug=True, port=5000)

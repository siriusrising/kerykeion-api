from flask import Flask, send_file, request

from pathlib import Path
from kerykeion import AstrologicalSubjectFactory
from kerykeion.chart_data_factory import ChartDataFactory
from kerykeion.charts.chart_drawer import ChartDrawer

app = Flask(__name__)


@app.route("/")
def home():
    return "Kerykeion API is running"


@app.route("/chart")
def chart():

    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    day = request.args.get("day", type=int)
    hour = request.args.get("hour", type=int)
    minute = request.args.get("minute", type=int)

    city = request.args.get("city")
    country = request.args.get("country")

    return {
        "year": year,
        "month": month,
        "day": day,
        "hour": hour,
        "minute": minute,
        "city": city,
        "country": country
    }


@app.route("/version")
def version():
    import kerykeion

    return {
        "version": kerykeion.__version__
    }


@app.route("/test")
def test_chart():

    subject = AstrologicalSubjectFactory.from_birth_data(
        "Sirius Rising",
        1957,
        1,
        20,
        9,
        0,
        lng=-4.1992427,
        lat=55.9731494,
        tz_str="Europe/London",
        online=False,
    )

    chart_data = ChartDataFactory.create_natal_chart_data(subject)

    drawer = ChartDrawer(chart_data=chart_data)

    out_dir = Path("charts")
    out_dir.mkdir(exist_ok=True)

    drawer.save_svg(
        output_path=out_dir,
        filename="test-chart"
    )

    return send_file(
        "charts/test-chart.svg",
        mimetype="image/svg+xml"
    )


if __name__ == "__main__":
    app.run(debug=True)

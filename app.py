import os
import logging
from flask import Flask, request, Response, jsonify
from kerykeion import AstrologicalSubjectFactory
from kerykeion.chart_data_factory import ChartDataFactory
from kerykeion.charts.chart_drawer import ChartDrawer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
app = Flask(__name__)

GEONAMES_USERNAME = os.environ.get("GEONAMES_USERNAME", "siriusrising")

SIGN_DESCRIPTIONS = {
    "Ari": ("Aries", "♈", "Bold, pioneering and fiercely independent. You charge ahead with courage and passion."),
    "Tau": ("Taurus", "♉", "Grounded, patient and deeply sensual. You seek stability, beauty and lasting comfort."),
    "Gem": ("Gemini", "♊", "Curious, quick-witted and endlessly adaptable. You thrive on communication and variety."),
    "Can": ("Cancer", "♋", "Intuitive, nurturing and deeply emotional. Home and family are your sanctuary."),
    "Leo": ("Leo", "♌", "Confident, generous and magnetic. You were born to shine and inspire others."),
    "Vir": ("Virgo", "♍", "Analytical, precise and devoted to service. You find meaning in the details."),
    "Lib": ("Libra", "♎", "Diplomatic, charming and justice-seeking. You thrive in harmony and partnership."),
    "Sco": ("Scorpio", "♏", "Intense, perceptive and powerfully transformative. You see beneath every surface."),
    "Sag": ("Sagittarius", "♐", "Philosophical, adventurous and freedom-loving. You seek truth and expansion."),
    "Cap": ("Capricorn", "♑", "Disciplined, ambitious and quietly powerful. You build lasting legacies."),
    "Aqu": ("Aquarius", "♒", "Original, humanitarian and intellectually visionary. You march to your own drum."),
    "Pis": ("Pisces", "♓", "Compassionate, imaginative and spiritually attuned. You feel everything deeply."),
}

PLANET_MEANINGS = {
    "Sun": "Your core identity and life purpose",
    "Moon": "Your emotional nature and instinctive responses",
    "Mercury": "How you think, communicate and process information",
    "Venus": "What you love, value and find beautiful",
    "Mars": "Your drive, ambition and how you take action",
    "Jupiter": "Where you find expansion, luck and abundance",
    "Saturn": "Where you face challenges, discipline and life lessons",
    "Uranus": "Where you seek freedom, originality and sudden change",
    "Neptune": "Where you dream, idealize and seek transcendence",
    "Pluto": "Where you experience deep transformation and power",
}

HOUSE_MEANINGS = {
    1: "Self & Identity",
    2: "Money & Values",
    3: "Communication & Mind",
    4: "Home & Family",
    5: "Creativity & Pleasure",
    6: "Health & Daily Life",
    7: "Relationships & Partnership",
    8: "Transformation & Shared Resources",
    9: "Philosophy & Travel",
    10: "Career & Public Life",
    11: "Friends & Hopes",
    12: "Spirituality & Hidden Matters",
}

def get_sign_info(sign_code):
    return SIGN_DESCRIPTIONS.get(sign_code, (sign_code, "?", ""))

@app.route("/")
def index():
    return """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
body { margin:0; display:flex; justify-content:center; align-items:center; height:100vh; background:#f7f4ec; font-family:Georgia,serif; }
.container { text-align:center; }
.hourglass { font-size:100px; animation:spin 2.5s linear infinite; display:inline-block; }
h1 { color:#1b355d; margin-top:20px; font-weight:normal; }
p { color:#666; }
@keyframes spin { from{transform:rotate(0deg);} to{transform:rotate(360deg);} }
</style>
</head>
<body>
<div class="container">
  <div class="hourglass">⏳</div>
  <h1>Your Chart is Ready to Generate</h1>
  <p>Enter your birth details above and click Generate</p>
</div>
</body>
</html>"""

@app.route("/test")
def test():
    subject = AstrologicalSubjectFactory.from_birth_data(
        name="Test",
        year=1957, month=1, day=20, hour=9, minute=0,
        lng=-4.1974, lat=55.9742,
        tz_str="Europe/London",
        online=False,
    )
    chart_data = ChartDataFactory.create_natal_chart_data(subject)
    drawer = ChartDrawer(chart_data=chart_data)
    return Response(drawer.generate_svg_string(), mimetype="image/svg+xml")

@app.route("/chart-page")
def chart_page():
    try:
        year   = int(request.args["year"])
        month  = int(request.args["month"])
        day    = int(request.args["day"])
        hour   = int(request.args.get("hour", 12))
        minute = int(request.args.get("minute", 0))
        city    = request.args["city"]
        country = request.args["country"]

        subject = AstrologicalSubjectFactory.from_birth_data(
            name="Chart",
            year=year, month=month, day=day,
            hour=hour, minute=minute,
            city=city, nation=country,
            geonames_username=GEONAMES_USERNAME,
            online=True
        )
        chart_data = ChartDataFactory.create_natal_chart_data(subject)
        drawer = ChartDrawer(chart_data=chart_data)
        svg = drawer.generate_svg_string()

        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
html, body {{ margin: 0; padding: 0; width: 100%; background: white; }}
svg {{ display: block; width: 100%; height: auto; }}
</style>
</head>
<body>{svg}</body>
</html>"""
        return Response(html, mimetype="text/html")

    except Exception as e:
        logger.exception(e)
        return jsonify({"error": "Chart generation failed", "detail": str(e)}), 500

@app.route("/interpret")
def interpret():
    try:
        year   = int(request.args["year"])
        month  = int(request.args["month"])
        day    = int(request.args["day"])
        hour   = int(request.args.get("hour", 12))
        minute = int(request.args.get("minute", 0))
        city    = request.args["city"]
        country = request.args["country"]
        name    = request.args.get("name", "Your")

        subject = AstrologicalSubjectFactory.from_birth_data(
            name=name,
            year=year, month=month, day=day,
            hour=hour, minute=minute,
            city=city, nation=country,
            geonames_username=GEONAMES_USERNAME,
            online=True
        )

        # ── Build planet rows ──────────────────────────────────────────────────
        planets = [
            ("Sun",     subject.sun),
            ("Moon",    subject.moon),
            ("Mercury", subject.mercury),
            ("Venus",   subject.venus),
            ("Mars",    subject.mars),
            ("Jupiter", subject.jupiter),
            ("Saturn",  subject.saturn),
            ("Uranus",  subject.uranus),
            ("Neptune", subject.neptune),
            ("Pluto",   subject.pluto),
        ]

        asc  = subject.first_house
        mc   = subject.tenth_house

        asc_name, asc_symbol, asc_desc = get_sign_info(asc.sign[:3])
        sun_name, sun_symbol, sun_desc = get_sign_info(subject.sun.sign[:3])
        moon_name, moon_symbol, moon_desc = get_sign_info(subject.moon.sign[:3])

        planet_rows = ""
        for pname, pobj in planets:
            sign_name, symbol, _ = get_sign_info(pobj.sign[:3])
            meaning = PLANET_MEANINGS.get(pname, "")
            house = getattr(pobj, "house", "")
            house_num = ""
            if house:
                try:
                    house_num = f" · House {int(''.join(filter(str.isdigit, str(house))))}"
                except:
                    pass
            planet_rows += f"""
            <tr>
                <td class="planet">{pname}</td>
                <td class="sign">{symbol} {sign_name}</td>
                <td class="house">{house_num}</td>
                <td class="meaning">{meaning}</td>
            </tr>"""

        # ── House cusp rows ────────────────────────────────────────────────────
        house_objects = [
            subject.first_house, subject.second_house, subject.third_house,
            subject.fourth_house, subject.fifth_house, subject.sixth_house,
            subject.seventh_house, subject.eighth_house, subject.ninth_house,
            subject.tenth_house, subject.eleventh_house, subject.twelfth_house,
        ]
        house_rows = ""
        for i, h in enumerate(house_objects, 1):
            sign_name, symbol, _ = get_sign_info(h.sign[:3])
            meaning = HOUSE_MEANINGS.get(i, "")
            house_rows += f"""
            <tr>
                <td class="planet">House {i}</td>
                <td class="sign">{symbol} {sign_name}</td>
                <td class="meaning" colspan="2">{meaning}</td>
            </tr>"""

        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Birth Chart Interpretation</title>
<style>
  body {{
    margin: 0;
    padding: 30px;
    font-family: Georgia, serif;
    background: #f7f4ec;
    color: #2c2c2c;
  }}
  .page {{
    max-width: 800px;
    margin: 0 auto;
    background: white;
    padding: 50px;
    box-shadow: 0 2px 20px rgba(0,0,0,0.08);
  }}
  h1 {{
    color: #1b355d;
    font-size: 28px;
    margin-bottom: 5px;
    font-weight: normal;
    text-align: center;
  }}
  .subtitle {{
    text-align: center;
    color: #888;
    font-size: 14px;
    margin-bottom: 40px;
  }}
  .big-three {{
    display: flex;
    justify-content: space-around;
    background: #1b355d;
    color: white;
    border-radius: 10px;
    padding: 25px;
    margin-bottom: 40px;
    text-align: center;
  }}
  .big-three .item .label {{
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 2px;
    opacity: 0.7;
    margin-bottom: 8px;
  }}
  .big-three .item .symbol {{
    font-size: 36px;
  }}
  .big-three .item .sign-name {{
    font-size: 18px;
    margin-top: 5px;
  }}
  .big-three .item .desc {{
    font-size: 12px;
    opacity: 0.8;
    margin-top: 8px;
    max-width: 180px;
  }}
  h2 {{
    color: #1b355d;
    font-size: 18px;
    font-weight: normal;
    border-bottom: 1px solid #e0d9c8;
    padding-bottom: 8px;
    margin-top: 40px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
  }}
  tr:nth-child(even) {{
    background: #f7f4ec;
  }}
  td {{
    padding: 10px 12px;
    vertical-align: top;
  }}
  .planet {{
    font-weight: bold;
    color: #1b355d;
    width: 100px;
  }}
  .sign {{
    width: 130px;
    color: #555;
  }}
  .house {{
    width: 90px;
    color: #888;
    font-size: 13px;
  }}
  .meaning {{
    color: #666;
    font-style: italic;
  }}
  .print-btn {{
    display: block;
    margin: 40px auto 0;
    padding: 14px 40px;
    background: #1b355d;
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 16px;
    font-family: Georgia, serif;
    cursor: pointer;
    letter-spacing: 1px;
  }}
  .print-btn:hover {{
    background: #2a4a7f;
  }}
  @media print {{
    body {{ background: white; padding: 0; }}
    .page {{ box-shadow: none; padding: 20px; }}
    .print-btn {{ display: none; }}
  }}
</style>
</head>
<body>
<div class="page">
  <h1>Birth Chart Summary</h1>
  <div class="subtitle">{city}, {country} &nbsp;·&nbsp; {day}/{month}/{year} &nbsp;·&nbsp; {hour:02d}:{minute:02d}</div>

  <div class="big-three">
    <div class="item">
      <div class="label">Sun Sign</div>
      <div class="symbol">{sun_symbol}</div>
      <div class="sign-name">{sun_name}</div>
      <div class="desc">{sun_desc}</div>
    </div>
    <div class="item">
      <div class="label">Moon Sign</div>
      <div class="symbol">{moon_symbol}</div>
      <div class="sign-name">{moon_name}</div>
      <div class="desc">{moon_desc}</div>
    </div>
    <div class="item">
      <div class="label">Rising Sign</div>
      <div class="symbol">{asc_symbol}</div>
      <div class="sign-name">{asc_name}</div>
      <div class="desc">{asc_desc}</div>
    </div>
  </div>

  <h2>Planetary Positions</h2>
  <table>{planet_rows}</table>

  <h2>House Cusps</h2>
  <table>{house_rows}</table>

  <button class="print-btn" onclick="window.print()">⬇ Download as PDF</button>
</div>
</body>
</html>"""
        return Response(html, mimetype="text/html")

    except Exception as e:
        logger.exception(e)
        return jsonify({"error": "Interpretation failed", "detail": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)

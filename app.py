import os
import logging
import requests
from flask import Flask, request, Response, jsonify
from kerykeion import AstrologicalSubjectFactory
from kerykeion.chart_data_factory import ChartDataFactory
from kerykeion.charts.chart_drawer import ChartDrawer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
app = Flask(__name__)

GEONAMES_USERNAME = os.environ.get("GEONAMES_USERNAME", "siriusrising")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

ZODIAC_SYMBOLS = {
    "Ari": ("♈", "#FF6B6B"), "Tau": ("♉", "#82C341"), "Gem": ("♊", "#FFD700"),
    "Can": ("♋", "#87CEEB"), "Leo": ("♌", "#FFA500"), "Vir": ("♍", "#9BC850"),
    "Lib": ("♎", "#FFB6C1"), "Sco": ("♏", "#8B0000"), "Sag": ("♐", "#9B59B6"),
    "Cap": ("♑", "#5D6D7E"), "Aqu": ("♒", "#3498DB"), "Pis": ("♓", "#1ABC9C"),
}

SIGN_NAMES = {
    "Ari": "Aries", "Tau": "Taurus", "Gem": "Gemini", "Can": "Cancer",
    "Leo": "Leo", "Vir": "Virgo", "Lib": "Libra", "Sco": "Scorpio",
    "Sag": "Sagittarius", "Cap": "Capricorn", "Aqu": "Aquarius", "Pis": "Pisces",
}

def get_sign_code(sign_str):
    return sign_str[:3] if sign_str else "Ari"

def call_groq(prompt):
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2000,
            "temperature": 0.8
        },
        timeout=30
    )
    data = response.json()
    logger.info("Groq response status: %s", response.status_code)
    if "choices" not in data:
        raise Exception(f"Groq error: {data}")
    return data["choices"][0]["message"]["content"]

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

        planet_lines = "\n".join(
            f"- {pname} in {pobj.sign} (House {getattr(pobj, 'house', '?')})"
            for pname, pobj in planets
        )

        asc_sign = subject.first_house.sign
        mc_sign  = subject.tenth_house.sign

        sun_code  = get_sign_code(subject.sun.sign)
        moon_code = get_sign_code(subject.moon.sign)
        asc_code  = get_sign_code(asc_sign)

        sun_symbol,  sun_color  = ZODIAC_SYMBOLS.get(sun_code,  ("☉", "#FFA500"))
        moon_symbol, moon_color = ZODIAC_SYMBOLS.get(moon_code, ("☽", "#87CEEB"))
        asc_symbol,  asc_color  = ZODIAC_SYMBOLS.get(asc_code,  ("↑", "#9B59B6"))

        sun_name  = SIGN_NAMES.get(sun_code,  subject.sun.sign)
        moon_name = SIGN_NAMES.get(moon_code, subject.moon.sign)
        asc_name  = SIGN_NAMES.get(asc_code,  asc_sign)

        prompt = f"""You are an experienced, warm and insightful astrologer. Write a personalised birth chart interpretation for {name}, born on {day}/{month}/{year} at {hour:02d}:{minute:02d} in {city}, {country}.

Their chart details:
- Ascendant (Rising Sign): {asc_sign}
- Midheaven (MC): {mc_sign}
{planet_lines}

Write a flowing, engaging interpretation of approximately 600-800 words. Cover:
1. A brief introduction about their overall chart energy
2. The Big Three (Sun, Moon and Rising) and what they reveal about personality, emotions and outer self
3. Key planetary placements and what they mean for this person's life
4. A warm, encouraging closing paragraph about their life path

Write directly to {name} in second person (you/your). Be warm, insightful and specific. Avoid generic statements. Do not use bullet points — write in flowing paragraphs."""

        interpretation = call_groq(prompt)

        paragraphs = [p.strip() for p in interpretation.split("\n\n") if p.strip()]
        html_content = "\n".join(f"<p>{p}</p>" for p in paragraphs)

        # Generate starfield SVG
        stars = ""
        import random
        random.seed(year + month + day)
        for _ in range(80):
            x = random.uniform(0, 800)
            y = random.uniform(0, 200)
            r = random.uniform(0.5, 2.5)
            op = random.uniform(0.4, 1.0)
            stars += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="white" opacity="{op:.2f}"/>'

        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Birth Chart Interpretation — {name}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: Georgia, serif; background: #f7f4ec; color: #2c2c2c; }}
  .page {{ max-width: 800px; margin: 0 auto; background: white; box-shadow: 0 2px 30px rgba(0,0,0,0.12); }}

  /* Starfield header */
  .header {{ position: relative; background: #0d1b2a; overflow: hidden; padding: 50px 40px 40px; text-align: center; }}
  .header svg {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; }}
  .header-content {{ position: relative; z-index: 2; }}
  .header h1 {{ color: white; font-size: 28px; font-weight: normal; letter-spacing: 2px; margin-bottom: 8px; }}
  .header .subtitle {{ color: rgba(255,255,255,0.6); font-size: 13px; letter-spacing: 1px; }}

  /* Big Three */
  .big-three {{ display: flex; justify-content: center; gap: 0; background: #0d1b2a; padding: 0 40px 40px; }}
  .sign-card {{ flex: 1; text-align: center; padding: 25px 15px; border-radius: 12px; margin: 0 8px; background: rgba(255,255,255,0.07); }}
  .sign-card .label {{ font-size: 10px; text-transform: uppercase; letter-spacing: 3px; color: rgba(255,255,255,0.5); margin-bottom: 12px; }}
  .sign-card .zodiac-symbol {{ font-size: 52px; line-height: 1; margin-bottom: 8px; }}
  .sign-card .sign-name {{ color: white; font-size: 16px; letter-spacing: 1px; }}

  /* Body */
  .body {{ padding: 50px; }}
  p {{ line-height: 1.9; font-size: 15px; color: #333; margin-bottom: 22px; }}
  p:first-child::first-letter {{ font-size: 48px; float: left; line-height: 0.8; margin: 8px 8px 0 0; color: #1b355d; font-weight: bold; }}

  /* Divider */
  .divider {{ text-align: center; color: #c8b89a; font-size: 22px; margin: 30px 0; letter-spacing: 8px; }}

  /* Print button */
  .print-btn {{ display: block; margin: 20px auto 0; padding: 14px 50px; background: #1b355d; color: white; border: none; border-radius: 6px; font-size: 15px; font-family: Georgia, serif; cursor: pointer; letter-spacing: 1px; }}
  .print-btn:hover {{ background: #2a4a7f; }}

  /* Footer */
  .footer {{ text-align: center; padding: 30px; color: #aaa; font-size: 12px; border-top: 1px solid #eee; }}

  @media print {{
    body {{ background: white; }}
    .page {{ box-shadow: none; }}
    .print-btn {{ display: none; }}
    .footer {{ display: none; }}
  }}
</style>
</head>
<body>
<div class="page">

  <div class="header">
    <svg viewBox="0 0 800 200" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">
      {stars}
      <!-- Moon crescent -->
      <circle cx="720" cy="50" r="35" fill="#f0e68c" opacity="0.15"/>
      <circle cx="735" cy="45" r="28" fill="#0d1b2a" opacity="1"/>
      <!-- Constellation dots -->
      <circle cx="100" cy="80" r="2" fill="white" opacity="0.8"/>
      <circle cx="130" cy="60" r="1.5" fill="white" opacity="0.7"/>
      <circle cx="160" cy="90" r="2" fill="white" opacity="0.9"/>
      <circle cx="145" cy="70" r="1" fill="white" opacity="0.6"/>
      <line x1="100" y1="80" x2="130" y2="60" stroke="white" stroke-width="0.5" opacity="0.3"/>
      <line x1="130" y1="60" x2="160" y2="90" stroke="white" stroke-width="0.5" opacity="0.3"/>
      <line x1="130" y1="60" x2="145" y2="70" stroke="white" stroke-width="0.5" opacity="0.3"/>
    </svg>
    <div class="header-content">
      <h1>✦ Birth Chart Interpretation ✦</h1>
      <div class="subtitle">{name} &nbsp;·&nbsp; {city}, {country} &nbsp;·&nbsp; {day}/{month}/{year} &nbsp;·&nbsp; {hour:02d}:{minute:02d}</div>
    </div>
  </div>

  <div class="big-three">
    <div class="sign-card">
      <div class="label">☉ Sun Sign</div>
      <div class="zodiac-symbol" style="color:{sun_color}">{sun_symbol}</div>
      <div class="sign-name">{sun_name}</div>
    </div>
    <div class="sign-card">
      <div class="label">☽ Moon Sign</div>
      <div class="zodiac-symbol" style="color:{moon_color}">{moon_symbol}</div>
      <div class="sign-name">{moon_name}</div>
    </div>
    <div class="sign-card">
      <div class="label">↑ Rising Sign</div>
      <div class="zodiac-symbol" style="color:{asc_color}">{asc_symbol}</div>
      <div class="sign-name">{asc_name}</div>
    </div>
  </div>

  <div class="body">
    <div class="divider">✦ ✦ ✦</div>
    {html_content}
    <div class="divider">✦ ✦ ✦</div>
    <button class="print-btn" onclick="window.print()">⬇ Download as PDF</button>
  </div>

  <div class="footer">
    Generated by The Tarot of Her &nbsp;·&nbsp; www.thetarotofher.com
  </div>

</div>
</body>
</html>"""
        return Response(html, mimetype="text/html")

    except Exception as e:
        logger.exception(e)
        return jsonify({"error": "Interpretation failed", "detail": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)

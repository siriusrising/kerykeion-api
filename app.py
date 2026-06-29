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

def call_groq(prompt):
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "llama3-70b-8192",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2000,
            "temperature": 0.8
        },
        timeout=30
    )
    data = response.json()
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

        # Build chart data summary for the prompt
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
        mc_sign = subject.tenth_house.sign

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

        # Convert line breaks to HTML paragraphs
        paragraphs = [p.strip() for p in interpretation.split("\n\n") if p.strip()]
        html_content = "\n".join(f"<p>{p}</p>" for p in paragraphs)

        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Birth Chart Interpretation — {name}</title>
<style>
  body {{ margin: 0; padding: 30px; font-family: Georgia, serif; background: #f7f4ec; color: #2c2c2c; }}
  .page {{ max-width: 800px; margin: 0 auto; background: white; padding: 50px; box-shadow: 0 2px 20px rgba(0,0,0,0.08); }}
  h1 {{ color: #1b355d; font-size: 28px; font-weight: normal; text-align: center; margin-bottom: 5px; }}
  .subtitle {{ text-align: center; color: #888; font-size: 14px; margin-bottom: 40px; }}
  .big-three {{ display: flex; justify-content: space-around; background: #1b355d; color: white; border-radius: 10px; padding: 20px; margin-bottom: 40px; text-align: center; }}
  .big-three .label {{ font-size: 11px; text-transform: uppercase; letter-spacing: 2px; opacity: 0.7; }}
  .big-three .sign {{ font-size: 18px; margin-top: 5px; }}
  p {{ line-height: 1.9; font-size: 15px; color: #333; margin-bottom: 20px; }}
  .print-btn {{ display: block; margin: 40px auto 0; padding: 14px 40px; background: #1b355d; color: white; border: none; border-radius: 6px; font-size: 16px; font-family: Georgia, serif; cursor: pointer; letter-spacing: 1px; }}
  .print-btn:hover {{ background: #2a4a7f; }}
  @media print {{ body {{ background: white; }} .page {{ box-shadow: none; }} .print-btn {{ display: none; }} }}
</style>
</head>
<body>
<div class="page">
  <h1>Birth Chart Interpretation</h1>
  <div class="subtitle">{name} &nbsp;·&nbsp; {city}, {country} &nbsp;·&nbsp; {day}/{month}/{year} &nbsp;·&nbsp; {hour:02d}:{minute:02d}</div>

  <div class="big-three">
    <div>
      <div class="label">Sun Sign</div>
      <div class="sign">{subject.sun.sign}</div>
    </div>
    <div>
      <div class="label">Moon Sign</div>
      <div class="sign">{subject.moon.sign}</div>
    </div>
    <div>
      <div class="label">Rising Sign</div>
      <div class="sign">{asc_sign}</div>
    </div>
  </div>

  {html_content}

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

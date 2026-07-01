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
    "Lib": ("♎", "#FFB6C1"), "Sco": ("♏", "#c44569"), "Sag": ("♐", "#9B59B6"),
    "Cap": ("♑", "#c9a96e"), "Aqu": ("♒", "#3498DB"), "Pis": ("♓", "#1ABC9C"),
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
  body { margin: 0; padding: 0; background: #0d1b2a; overflow: hidden; font-family: Georgia, serif; }
  canvas { position: absolute; top: 0; left: 0; }
  .content { position: relative; z-index: 2; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; text-align: center; padding: 20px; }
  .brand { color: #c9a96e; font-size: 10px; letter-spacing: 4px; text-transform: uppercase; margin-bottom: 14px; }
  .heading { color: white; font-size: 28px; font-weight: 300; font-style: italic; margin-bottom: 10px; }
  .divider { color: #c9a96e; font-size: 16px; letter-spacing: 8px; margin: 16px 0; }
  .subtitle { color: rgba(255,255,255,0.45); font-size: 13px; letter-spacing: 1px; }
</style>
</head>
<body>
<canvas id="c"></canvas>
<div class="content">
  <div class="brand">✦ The Tarot of Her ✦</div>
  <div class="heading">Birth Chart Calculator</div>
  <div class="divider">✦ ✦ ✦</div>
  <div class="subtitle">Enter your details above and click Generate My Chart</div>
</div>
<script>
const canvas = document.getElementById('c');
const ctx = canvas.getContext('2d');
const SIGNS = ['♈','♉','♊','♋','♌','♍','♎','♏','♐','♑','♒','♓'];
const COLORS = ['#FF6B6B','#82C341','#FFD700','#87CEEB','#FFA500','#9BC850','#FFB6C1','#c44569','#9B59B6','#c9a96e','#3498DB','#1ABC9C'];
let stars = [], symbols = [];
let W, H;

function resize() {
  W = canvas.width = window.innerWidth || 680;
  H = canvas.height = window.innerHeight || 400;
}

function init() {
  resize();
  stars = [];
  for (let i = 0; i < 180; i++) {
    stars.push({
      x: Math.random() * W, y: Math.random() * H,
      r: Math.random() * 1.5 + 0.2,
      alpha: Math.random(),
      speed: Math.random() * 0.004 + 0.001,
      phase: Math.random() * Math.PI * 2
    });
  }
  symbols = [];
  for (let i = 0; i < 18; i++) {
    const idx = i % 12;
    symbols.push({
      sign: SIGNS[idx],
      color: COLORS[idx],
      x: Math.random() * W,
      y: Math.random() * H,
      size: Math.random() * 22 + 14,
      speedX: (Math.random() - 0.5) * 0.4,
      speedY: (Math.random() - 0.5) * 0.3,
      alpha: Math.random() * 0.4 + 0.15,
      phase: Math.random() * Math.PI * 2,
      pulseSpeed: Math.random() * 0.003 + 0.001
    });
  }
}

function draw(t) {
  ctx.fillStyle = '#0d1b2a';
  ctx.fillRect(0, 0, W, H);

  stars.forEach(s => {
    s.alpha = 0.2 + 0.7 * Math.abs(Math.sin(t * s.speed + s.phase));
    ctx.beginPath();
    ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(255,255,255,' + s.alpha + ')';
    ctx.fill();
  });

  ctx.beginPath();
  ctx.arc(W - 70, 55, 28, 0, Math.PI * 2);
  ctx.fillStyle = 'rgba(201,169,110,0.1)';
  ctx.fill();
  ctx.beginPath();
  ctx.arc(W - 58, 50, 22, 0, Math.PI * 2);
  ctx.fillStyle = '#0d1b2a';
  ctx.fill();

  symbols.forEach(s => {
    s.x += s.speedX;
    s.y += s.speedY;
    if (s.x < -40) s.x = W + 20;
    if (s.x > W + 40) s.x = -20;
    if (s.y < -40) s.y = H + 20;
    if (s.y > H + 40) s.y = -20;
    const pulse = s.alpha + 0.1 * Math.sin(t * s.pulseSpeed + s.phase);
    ctx.save();
    ctx.globalAlpha = Math.max(0.1, Math.min(0.6, pulse));
    ctx.font = s.size + 'px Georgia';
    ctx.fillStyle = s.color;
    ctx.fillText(s.sign, s.x, s.y);
    ctx.restore();
  });

  requestAnimationFrame(draw);
}

init();
window.addEventListener('resize', init);
requestAnimationFrame(draw);
</script>
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

        import random
        random.seed(year + month + day)
        stars = ""
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
  .header {{ position: relative; background: #0d1b2a; overflow: hidden; padding: 50px 40px 40px; text-align: center; }}
  .header svg {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; }}
  .header-content {{ position: relative; z-index: 2; }}
  .header h1 {{ color: white; font-size: 28px; font-weight: normal; letter-spacing: 2px; margin-bottom: 8px; }}
  .header .subtitle {{ color: rgba(255,255,255,0.6); font-size: 13px; letter-spacing: 1px; }}
  .header .gold {{ color: #c9a96e; font-size: 11px; letter-spacing: 4px; text-transform: uppercase; margin-bottom: 12px; }}
  .big-three {{ display: flex; justify-content: center; gap: 0; background: #0d1b2a; padding: 0 30px 30px; }}
  .sign-card {{ flex: 1; text-align: center; padding: 20px 10px; border-radius: 10px; margin: 0 6px; background: rgba(201,169,110,0.1); border: 1px solid rgba(201,169,110,0.2); }}
  .sign-label {{ font-size: 9px; letter-spacing: 3px; color: rgba(201,169,110,0.7); text-transform: uppercase; margin-bottom: 8px; }}
  .sign-symbol {{ font-size: 40px; line-height: 1; margin-bottom: 6px; }}
  .sign-name {{ color: white; font-size: 15px; font-style: italic; }}
  .body {{ padding: 50px; }}
  .divider {{ text-align: center; color: #c9a96e; font-size: 14px; letter-spacing: 6px; margin: 20px 0; }}
  p {{ line-height: 1.9; font-size: 15px; color: #333; margin-bottom: 22px; }}
  p:first-of-type::first-letter {{ font-size: 48px; float: left; line-height: 0.8; margin: 8px 8px 0 0; color: #c9a96e; font-weight: bold; }}
  .print-btn {{ display: block; margin: 20px auto 0; padding: 14px 50px; background: #1b2d4f; color: #c9a96e; border: none; border-radius: 4px; font-family: Georgia, serif; font-size: 13px; letter-spacing: 2px; cursor: pointer; text-transform: uppercase; }}
  .print-btn:hover {{ background: #2a4a7f; }}
  .footer {{ text-align: center; padding: 25px; color: #aaa; font-size: 11px; letter-spacing: 2px; border-top: 1px solid #eee; margin-top: 40px; }}
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
      <circle cx="720" cy="50" r="35" fill="#c9a96e" opacity="0.12"/>
      <circle cx="735" cy="45" r="28" fill="#0d1b2a" opacity="1"/>
    </svg>
    <div class="header-content">
      <div class="gold">✦ Birth Chart Interpretation ✦</div>
      <h1>{name}</h1>
      <div class="subtitle">{city}, {country} &nbsp;·&nbsp; {day}/{month}/{year} &nbsp;·&nbsp; {hour:02d}:{minute:02d}</div>
    </div>
  </div>

  <div class="big-three">
    <div class="sign-card">
      <div class="sign-label">☉ Sun Sign</div>
      <div class="sign-symbol" style="color:{sun_color}">{sun_symbol}</div>
      <div class="sign-name">{sun_name}</div>
    </div>
    <div class="sign-card">
      <div class="sign-label">☽ Moon Sign</div>
      <div class="sign-symbol" style="color:{moon_color}">{moon_symbol}</div>
      <div class="sign-name">{moon_name}</div>
    </div>
    <div class="sign-card">
      <div class="sign-label">↑ Rising Sign</div>
      <div class="sign-symbol" style="color:{asc_color}">{asc_symbol}</div>
      <div class="sign-name">{asc_name}</div>
    </div>
  </div>

  <div class="body">
    <div class="divider">✦ ✦ ✦</div>
    {html_content}
    <div class="divider">✦ ✦ ✦</div>
    <button class="print-btn" onclick="window.print()">⬇ Download as PDF</button>
  </div>

  <div class="footer">The Tarot of Her &nbsp;✦&nbsp; www.thetarotofher.com</div>
</div>
</body>
</html>"""
        return Response(html, mimetype="text/html")

    except Exception as e:
        logger.exception(e)
        return jsonify({"error": "Interpretation failed", "detail": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)

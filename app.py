import os
import time
import uuid
import random
import logging
import requests
import weasyprint
from flask import Flask, request, Response, jsonify
from kerykeion import AstrologicalSubjectFactory
from kerykeion.chart_data_factory import ChartDataFactory
from kerykeion.charts.chart_drawer import ChartDrawer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
app = Flask(__name__)

GEONAMES_USERNAME = os.environ.get("GEONAMES_USERNAME", "siriusrising")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# Short-lived cache so the "Download as PDF" button reuses the exact same
# generated HTML the person is already looking at, instead of firing a
# second Groq call that could come back with slightly different wording.
REPORT_CACHE = {}
CACHE_TTL_SECONDS = 3600


def cache_store(token, html):
    now = time.time()
    REPORT_CACHE[token] = (now, html)
    # light housekeeping: drop anything older than the TTL
    expired = [k for k, (ts, _) in REPORT_CACHE.items() if now - ts > CACHE_TTL_SECONDS]
    for k in expired:
        REPORT_CACHE.pop(k, None)


def cache_get(token):
    entry = REPORT_CACHE.get(token)
    if not entry:
        return None
    ts, html = entry
    if time.time() - ts > CACHE_TTL_SECONDS:
        REPORT_CACHE.pop(token, None)
        return None
    return html

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

# Symbols/colors for the modern & sensitive points shown on the new report page.
MODERN_POINT_SYMBOLS = {
    "chiron":      ("⚷", "#8E44AD"),
    "lilith":      ("⚸", "#C0392B"),
    "north_node":  ("☊", "#16A085"),
    "south_node":  ("☋", "#7F8C8D"),
    "fortune":     ("⊗", "#D4AC0D"),
}

# Every point we ever need across all routes. Passing this consistently means
# /chart-page will also *draw* Chiron, Lilith and the Nodes on the wheel, not
# just the text reports.
ACTIVE_POINTS = [
    "Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn",
    "Uranus", "Neptune", "Pluto",
    "Mean_North_Lunar_Node", "Mean_South_Lunar_Node",
    "Chiron", "Mean_Lilith",
    "Pars_Fortunae",
    "Ascendant", "Medium_Coeli",
]


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


def build_subject(name, year, month, day, hour, minute, city, country):
    return AstrologicalSubjectFactory.from_birth_data(
        name=name,
        year=year, month=month, day=day,
        hour=hour, minute=minute,
        city=city, nation=country,
        geonames_username=GEONAMES_USERNAME,
        online=True,
        active_points=ACTIVE_POINTS,
    )


def stars_svg(seed_year, seed_month, seed_day, count=80, w=800, h=200):
    random.seed(seed_year + seed_month + seed_day)
    out = ""
    for _ in range(count):
        x = random.uniform(0, w)
        y = random.uniform(0, h)
        r = random.uniform(0.5, 2.5)
        op = random.uniform(0.4, 1.0)
        out += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="white" opacity="{op:.2f}"/>'
    return out


REPORT_STYLE = """
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: Georgia, serif; background: #f7f4ec; color: #2c2c2c; }
  .page { max-width: 800px; margin: 0 auto; background: white; box-shadow: 0 2px 30px rgba(0,0,0,0.12); }
  .header { position: relative; background: #0d1b2a; overflow: hidden; padding: 50px 40px 40px; text-align: center; }
  .header svg { position: absolute; top: 0; left: 0; width: 100%; height: 100%; }
  .header-content { position: relative; z-index: 2; }
  .header h1 { color: white; font-size: 28px; font-weight: normal; letter-spacing: 2px; margin-bottom: 8px; }
  .header .subtitle { color: rgba(255,255,255,0.6); font-size: 13px; letter-spacing: 1px; }
  .header .gold { color: #c9a96e; font-size: 11px; letter-spacing: 4px; text-transform: uppercase; margin-bottom: 12px; }
  .big-three { display: flex; flex-wrap: wrap; justify-content: center; gap: 0; background: #0d1b2a; padding: 0 20px 30px; }
  .sign-card { flex: 1; min-width: 110px; text-align: center; padding: 20px 8px; border-radius: 10px; margin: 6px; background: rgba(201,169,110,0.1); border: 1px solid rgba(201,169,110,0.2); }
  .sign-label { font-size: 9px; letter-spacing: 2px; color: rgba(201,169,110,0.7); text-transform: uppercase; margin-bottom: 8px; }
  .sign-symbol { font-size: 36px; line-height: 1; margin-bottom: 6px; }
  .sign-name { color: white; font-size: 14px; font-style: italic; }
  .sign-house { color: rgba(255,255,255,0.45); font-size: 10px; letter-spacing: 1px; margin-top: 4px; }
  .body { padding: 50px; }
  .divider { text-align: center; color: #c9a96e; font-size: 14px; letter-spacing: 6px; margin: 20px 0; }
  p { line-height: 1.9; font-size: 15px; color: #333; margin-bottom: 22px; }
  p:first-of-type::first-letter { font-size: 44px; float: left; line-height: 1; padding-top: 4px; padding-right: 6px; padding-bottom: 2px; color: #c9a96e; font-weight: bold; }
  .print-btn { display: inline-block; margin-top: 20px; padding: 14px 50px; background: #1b2d4f; color: #c9a96e; border: none; border-radius: 4px; font-family: Georgia, serif; font-size: 13px; letter-spacing: 2px; cursor: pointer; text-transform: uppercase; text-decoration: none; }
  .print-btn-wrap { text-align: center; }
  .print-btn:hover { background: #2a4a7f; }
  .footer { text-align: center; padding: 25px; color: #aaa; font-size: 11px; letter-spacing: 2px; border-top: 1px solid #eee; margin-top: 40px; }
  @media print {
    @page { margin: 0; }
    body { background: white; margin: 0; }
    .page { box-shadow: none; padding: 1.5cm; }
    .print-btn { display: none; }
    .footer { display: none; }
  }
"""


def safe_filename(name):
    cleaned = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()
    return cleaned.replace(" ", "-") or "birth-chart"


def render_report_page(title_label, name, city, country, day, month, year, hour, minute,
                        cards_html, html_content, pdf_url=None):
    stars = stars_svg(year, month, day)
    button_html = ""
    if pdf_url:
        button_html = (
            f'<div class="print-btn-wrap"><a class="print-btn" href="{pdf_url}" '
            f'download="{safe_filename(name)}-birth-chart.pdf">⬇ Download as PDF</a></div>'
        )
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title_label} — {name}</title>
<style>{REPORT_STYLE}</style>
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
      <div class="gold">✦ {title_label} ✦</div>
      <h1>{name}</h1>
      <div class="subtitle">{city}, {country} &nbsp;·&nbsp; {day}/{month}/{year} &nbsp;·&nbsp; {hour:02d}:{minute:02d}</div>
    </div>
  </div>

  <div class="big-three">
    {cards_html}
  </div>

  <div class="body">
    <div class="divider">✦ ✦ ✦</div>
    {html_content}
    <div class="divider">✦ ✦ ✦</div>
    {button_html}
  </div>

  <div class="footer">The Tarot of Her &nbsp;✦&nbsp; www.thetarotofher.com</div>
</div>
</body>
</html>"""


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
  .title { color: #c9a96e; font-size: 11px; letter-spacing: 4px; text-transform: uppercase; margin-bottom: 16px; }
  .heading { color: white; font-size: 28px; font-weight: 300; font-style: italic; margin-bottom: 12px; }
  .subtitle { color: rgba(255,255,255,0.5); font-size: 13px; letter-spacing: 1px; }
  .divider { color: #c9a96e; font-size: 16px; letter-spacing: 8px; margin: 20px 0; }
</style>
</head>
<body>
<canvas id="c"></canvas>
<div class="content">
  <div class="title">✦ The Tarot of Her ✦</div>
  <div class="heading">Birth Chart Calculator</div>
  <div class="divider">✦ ✦ ✦</div>
  <div class="subtitle">Enter your details above and click Generate My Chart</div>
</div>
<script>
  const canvas = document.getElementById('c');
  const ctx = canvas.getContext('2d');
  let stars = [];
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
        x: Math.random() * W,
        y: Math.random() * H,
        r: Math.random() * 1.8 + 0.2,
        alpha: Math.random(),
        speed: Math.random() * 0.005 + 0.002,
        phase: Math.random() * Math.PI * 2
      });
    }
  }

  function draw(t) {
    ctx.fillStyle = '#0d1b2a';
    ctx.fillRect(0, 0, W, H);
    stars.forEach(s => {
      s.alpha = 0.3 + 0.7 * Math.abs(Math.sin(t * s.speed + s.phase));
      ctx.beginPath();
      ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(255,255,255,' + s.alpha + ')';
      ctx.fill();
    });
    ctx.beginPath();
    ctx.arc(W - 80, 60, 30, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(201,169,110,0.12)';
    ctx.fill();
    ctx.beginPath();
    ctx.arc(W - 68, 55, 24, 0, Math.PI * 2);
    ctx.fillStyle = '#0d1b2a';
    ctx.fill();
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
        active_points=ACTIVE_POINTS,
    )
    chart_data = ChartDataFactory.create_natal_chart_data(subject, active_points=ACTIVE_POINTS)
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

        subject = build_subject("Chart", year, month, day, hour, minute, city, country)
        chart_data = ChartDataFactory.create_natal_chart_data(subject, active_points=ACTIVE_POINTS)
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


def build_interpretation_html(name, year, month, day, hour, minute, city, country, pdf_url=None):
    subject = build_subject(name, year, month, day, hour, minute, city, country)

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

    chiron      = subject.chiron
    lilith      = subject.mean_lilith
    north_node  = subject.mean_north_lunar_node
    south_node  = subject.mean_south_lunar_node
    fortune     = subject.pars_fortunae

    modern_points = [
        ("Chiron (the wound that becomes wisdom)", chiron),
        ("Black Moon Lilith (the raw, instinctual self)", lilith),
        ("North Node (growth direction / soul purpose this lifetime)", north_node),
        ("South Node (innate gifts / old patterns to move beyond)", south_node),
        ("Part of Fortune (where ease and good fortune flow)", fortune),
    ]

    modern_lines = "\n".join(
        f"- {pname}: {pobj.sign} (House {getattr(pobj, 'house', '?')})"
        for pname, pobj in modern_points
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

Their modern & sensitive points:
{modern_lines}

Write a flowing, engaging interpretation of approximately 900-1200 words. Cover:
1. A brief introduction about their overall chart energy
2. The Big Three (Sun, Moon and Rising) and what they reveal about personality, emotions and outer self
3. Key planetary placements and what they mean for this person's life
4. Their deeper layer — Chiron (the core wound that becomes a gift once faced honestly), Black Moon Lilith (the instinctual, unapologetic part of them), and the Nodal axis together (the pull between old comfortable patterns and the growth path this lifetime is asking for). Weave in a brief, warm note on the Part of Fortune too.
5. A warm, encouraging closing paragraph about their life path

Write directly to {name} in second person (you/your). Be warm, insightful and specific. Avoid generic statements. Keep an emotionally intelligent, non-fatalistic tone for the Chiron/Lilith/Nodes section — these are invitations, not verdicts. Do not use bullet points — write in flowing paragraphs."""

    interpretation = call_groq(prompt)

    paragraphs = [p.strip() for p in interpretation.split("\n\n") if p.strip()]
    html_content = "\n".join(f"<p>{p}</p>" for p in paragraphs)

    def modern_card(label, symbol_key, pobj):
        symbol, color = MODERN_POINT_SYMBOLS[symbol_key]
        sign_code = get_sign_code(pobj.sign)
        sign_name = SIGN_NAMES.get(sign_code, pobj.sign)
        house = str(getattr(pobj, "house", "")).replace("_", " ")
        return f"""
    <div class="sign-card">
      <div class="sign-label">{label}</div>
      <div class="sign-symbol" style="color:{color}">{symbol}</div>
      <div class="sign-name">{sign_name}</div>
      <div class="sign-house">{house}</div>
    </div>"""

    cards_html = f"""
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
    </div>""" + (
        modern_card("⚷ Chiron", "chiron", chiron)
        + modern_card("⚸ Lilith", "lilith", lilith)
        + modern_card("☊ North Node", "north_node", north_node)
        + modern_card("☋ South Node", "south_node", south_node)
        + modern_card("⊗ Fortune", "fortune", fortune)
    )

    return render_report_page(
        "Birth Chart Interpretation", name, city, country, day, month, year, hour, minute,
        cards_html, html_content, pdf_url=pdf_url
    )


def parse_common_args(args):
    year   = int(args["year"])
    month  = int(args["month"])
    day    = int(args["day"])
    hour   = int(args.get("hour", 12))
    minute = int(args.get("minute", 0))
    city    = args["city"]
    country = args["country"]
    name    = args.get("name", "Your")
    return name, year, month, day, hour, minute, city, country


@app.route("/interpret")
def interpret():
    try:
        name, year, month, day, hour, minute, city, country = parse_common_args(request.args)

        token = uuid.uuid4().hex[:12]
        pdf_url = f"/interpret-pdf?token={token}"

        html = build_interpretation_html(name, year, month, day, hour, minute, city, country, pdf_url=pdf_url)
        cache_store(token, html)

        return Response(html, mimetype="text/html")

    except Exception as e:
        logger.exception(e)
        return jsonify({"error": "Interpretation failed", "detail": str(e)}), 500


@app.route("/interpret-pdf")
def interpret_pdf():
    try:
        token = request.args.get("token")
        html = cache_get(token) if token else None

        if html is None:
            # No cache hit (expired, or someone linked directly to this route) —
            # fall back to generating fresh. pdf_url=None hides the download
            # button inside the PDF itself, since it would be meaningless there.
            name, year, month, day, hour, minute, city, country = parse_common_args(request.args)
            html = build_interpretation_html(name, year, month, day, hour, minute, city, country, pdf_url=None)
        else:
            name = request.args.get("name", "Your")

        pdf_bytes = weasyprint.HTML(string=html).write_pdf()

        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_filename(name)}-birth-chart.pdf"'
            }
        )

    except Exception as e:
        logger.exception(e)
        return jsonify({"error": "PDF generation failed", "detail": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)

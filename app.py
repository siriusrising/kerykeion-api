import os
import re
import time
import uuid
import random
import base64
import logging
import requests
import weasyprint
from io import BytesIO
from PIL import Image
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, request, Response, jsonify, send_file
from kerykeion import AstrologicalSubjectFactory
from kerykeion.chart_data_factory import ChartDataFactory
from kerykeion.charts.chart_drawer import ChartDrawer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

GEONAMES_USERNAME = os.environ.get("GEONAMES_USERNAME", "siriusrising")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

REPORT_CACHE = {}
CACHE_TTL_SECONDS = 3600

def cache_store(token, html):
    now = time.time()
    REPORT_CACHE[token] = (now, html)
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

MODERN_POINT_SYMBOLS = {
    "chiron":      ("⚷", "#8E44AD"),
    "lilith":      ("⚸", "#C0392B"),
    "north_node":  ("☊", "#16A085"),
    "south_node":  ("☋", "#7F8C8D"),
    "fortune":     ("⊗", "#D4AC0D"),
}

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
            "model": "llama-3.1-8b-instant",
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
  .section-heading { color: #8a6d3b; font-size: 19px; font-style: italic; font-weight: normal; letter-spacing: 1px; margin: 34px 0 12px; padding-bottom: 8px; border-bottom: 1px solid rgba(201,169,110,0.35); }
  .section-heading:first-of-type { margin-top: 0; }
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

TAROT_PDF_STYLE = """
  .question-callout { text-align: center; font-style: italic; color: #8a6d3b; font-size: 16px; margin: 0 0 30px; padding: 18px; border-top: 1px solid rgba(201,169,110,0.35); border-bottom: 1px solid rgba(201,169,110,0.35); }
  .card-grid { display: flex; flex-wrap: wrap; justify-content: center; gap: 18px; margin-bottom: 10px; }
  .tarot-card { width: 140px; text-align: center; }
  .tarot-card img { width: 100%; border-radius: 6px; box-shadow: 0 2px 10px rgba(0,0,0,0.15); }
  .tarot-card img.reversed { transform: rotate(180deg); }
  .tarot-card .position-label { font-size: 10px; letter-spacing: 1.5px; text-transform: uppercase; color: #8a6d3b; margin-top: 8px; }
  .tarot-card .card-title { font-size: 13px; font-style: italic; color: #333; margin-top: 2px; }
  .journey-heading { text-align: center; color: #8a6d3b; font-size: 20px; font-style: italic; margin: 40px 0 20px; }
"""

SYNASTRY_PDF_STYLE = """
  .couple-names { display: flex; flex-wrap: wrap; justify-content: center; align-items: center; gap: 18px; background: #0d1b2a; padding: 0 20px 30px; }
  .couple-name-block { text-align: center; padding: 10px 16px; }
  .couple-name { color: white; font-size: 20px; font-style: italic; }
  .couple-meta { color: rgba(255,255,255,0.5); font-size: 11px; letter-spacing: 1px; margin-top: 4px; }
  .couple-ampersand { color: #c9a96e; font-size: 22px; }
"""

def safe_filename(name):
    cleaned = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()
    return cleaned.replace(" ", "-") or "birth-chart"

SECTION_HEADING_RE = re.compile(
    r'^##\s*(.+?)\s*$\n+(.*?)(?=^##\s*.+?$\n|\Z)',
    re.MULTILINE | re.DOTALL
)

def format_sectioned_interpretation(text):
    text = text.strip()
    matches = SECTION_HEADING_RE.findall(text)
    if not matches:
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        return "\n".join(f"<p>{p}</p>" for p in paragraphs)
    parts = []
    for heading, body in matches:
        body_paragraphs = [p.strip() for p in body.strip().split("\n\n") if p.strip()]
        if not body_paragraphs:
            continue
        body_html = "\n".join(f"<p>{p}</p>" for p in body_paragraphs)
        parts.append(f'<h2 class="section-heading">{heading.strip()}</h2>\n{body_html}')
    return "\n".join(parts)

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
  <div class="footer">Oraclyn &nbsp;✦&nbsp; www.oraclyn.fr</div>
</div>
</body>
</html>"""

MAX_PDF_IMAGE_WIDTH = 400

def fetch_image_as_data_uri(url, timeout=8):
    try:
        response = requests.get(url, timeout=timeout)
        if not response.ok:
            logger.warning("Image fetch failed (%s): %s", response.status_code, url)
            return None
        image = Image.open(BytesIO(response.content))
        image = image.convert("RGB")
        if image.width > MAX_PDF_IMAGE_WIDTH:
            ratio = MAX_PDF_IMAGE_WIDTH / image.width
            new_size = (MAX_PDF_IMAGE_WIDTH, int(image.height * ratio))
            image = image.resize(new_size, Image.LANCZOS)
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=80)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{encoded}"
    except Exception as e:
        logger.warning("Image fetch/resize error for %s: %s", url, e)
        return None

def prefetch_card_images(cards):
    results = [None] * len(cards)
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_index = {
            executor.submit(fetch_image_as_data_uri, card.get("image", "")): i
            for i, card in enumerate(cards)
        }
        for future in as_completed(future_to_index):
            i = future_to_index[future]
            results[i] = future.result()
    updated_cards = []
    for card, data_uri in zip(cards, results):
        new_card = dict(card)
        if data_uri:
            new_card["image"] = data_uri
        updated_cards.append(new_card)
    return updated_cards

def render_celtic_cross_pdf_html(question, cards, summary):
    stars = stars_svg(7, 7, 2026)
    card_tiles = []
    for card in cards:
        image_url = card.get("image", "")
        orientation = (card.get("orientation") or "upright").strip().lower()
        img_class = "reversed" if orientation == "reversed" else ""
        position = card.get("position", "")
        title = card.get("title", "")
        card_tiles.append(f"""
    <div class="tarot-card">
      <img class="{img_class}" src="{image_url}" alt="{title}">
      <div class="position-label">{position}</div>
      <div class="card-title">{title}{' (reversed)' if orientation == 'reversed' else ''}</div>
    </div>""")
    cards_html = "".join(card_tiles)
    summary_paragraphs = [p.strip() for p in summary.strip().split("\n\n") if p.strip()]
    summary_html = "\n".join(f"<p>{p}</p>" for p in summary_paragraphs)
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Your Celtic Cross Journey</title>
<style>{REPORT_STYLE}{TAROT_PDF_STYLE}</style>
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
      <div class="gold">✦ Celtic Cross Spread ✦</div>
      <h1>Your Journey</h1>
      <div class="subtitle">Oraclyn &nbsp;·&nbsp; www.oraclyn.fr</div>
    </div>
  </div>
  <div class="body">
    <div class="question-callout">"{question}"</div>
    <div class="card-grid">
      {cards_html}
    </div>
    <div class="journey-heading">✦ The Journey ✦</div>
    {summary_html}
  </div>
  <div class="footer">Oraclyn &nbsp;✦&nbsp; www.oraclyn.fr</div>
</div>
</body>
</html>"""

def render_synastry_pdf_html(name1, city1, country1, name2, city2, country2, html_content):
    stars = stars_svg(7, 7, 2026)
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Full Compatibility Report — {name1} &amp; {name2}</title>
<style>{REPORT_STYLE}{SYNASTRY_PDF_STYLE}</style>
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
      <div class="gold">✦ Full Compatibility Report ✦</div>
      <h1>{name1} &amp; {name2}</h1>
    </div>
  </div>
  <div class="couple-names">
    <div class="couple-name-block">
      <div class="couple-name">{name1}</div>
      <div class="couple-meta">{city1}, {country1}</div>
    </div>
    <div class="couple-ampersand">✦</div>
    <div class="couple-name-block">
      <div class="couple-name">{name2}</div>
      <div class="couple-meta">{city2}, {country2}</div>
    </div>
  </div>
  <div class="body">
    <div class="divider">✦ ✦ ✦</div>
    {html_content}
    <div class="divider">✦ ✦ ✦</div>
  </div>
  <div class="footer">Oraclyn &nbsp;✦&nbsp; www.oraclyn.fr</div>
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
  <div class="title">✦ Oraclyn ✦</div>
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

Structure your response using EXACTLY these section headings, in this exact order, each on its own line starting with "## " (two hash symbols and a space), with the section's writing directly beneath it. Do not add, remove, rename, or reorder headings. Do not use any other markdown (no bullet points, no bold, no numbered lists) — just plain flowing paragraphs under each heading:
## Your Chart at a Glance
## Sun
## Moon
## Ascendant
## Key Planetary Placements
## Chiron
## Lilith
## The Lunar Nodes
## Part of Fortune
## Your Path Forward

Guidance for each section:
- Your Chart at a Glance: a brief, engaging introduction to their overall chart energy (2-3 sentences).
- Sun / Moon / Ascendant: what each reveals about their personality, emotions, and outer self — one focused paragraph each.
- Key Planetary Placements: Mercury, Venus, Mars, Jupiter, Saturn, Uranus, Neptune and Pluto woven into flowing paragraphs (not a list), covering what matters most for this person's life.
- Chiron: the core wound, and how it becomes a gift once faced honestly.
- Lilith: the instinctual, unapologetic part of {name} that may have been suppressed or misunderstood, and how to reclaim it.
- The Lunar Nodes: the pull between old comfortable patterns (South Node) and the growth path this lifetime is asking for (North Node).
- Part of Fortune: a short, warm note on where natural ease and good fortune show up for them.
- Your Path Forward: a warm, encouraging closing paragraph about their life path, tying the themes together.

Total length approximately 900-1200 words across all sections. Write directly to {name} in second person (you/your). Be warm, insightful and specific — avoid generic statements. Keep an emotionally intelligent, non-fatalistic tone for the Chiron/Lilith/Nodes sections — these are invitations, not verdicts."""

    interpretation = call_groq(prompt)
    html_content = format_sectioned_interpretation(interpretation)

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

@app.route("/tarot-reading", methods=["POST"])
def tarot_reading():
    try:
        data = request.get_json(force=True, silent=True) or {}
        card_title = (data.get("cardTitle") or "").strip()
        upright = (data.get("upright") or "").strip()
        reversed_meaning = (data.get("reversedMeaning") or "").strip()
        animal = (data.get("animal") or "").strip()
        animal_meaning = (data.get("animalMeaning") or "").strip()
        question = (data.get("question") or "").strip()
        orientation = (data.get("orientation") or "upright").strip().lower()
        is_reversed = orientation == "reversed"
        if not card_title:
            return jsonify({"error": "cardTitle is required"}), 400
        if not question:
            question = "What do I need to know right now?"
        if is_reversed:
            if reversed_meaning:
                grounding = f'This card was drawn reversed. Its reversed meaning in this deck: "{reversed_meaning}"'
            else:
                grounding = (
                    f'This card was drawn reversed. No specific written reversed meaning was provided — '
                    f'interpret it as the upright meaning turned inward: blocked, delayed, internalized, or '
                    f'not yet fully expressed, rather than a "bad" or punishing version of the card. '
                    f'Its upright meaning for reference: "{upright}"' if upright else
                    'interpret it as this card\'s energy turned inward: blocked, delayed, or not yet fully '
                    'expressed, rather than a "bad" or punishing version of the card.'
                )
        else:
            grounding = (
                f'Its core meaning in this deck: "{upright}"'
                if upright
                else "No specific written meaning was provided for this card — draw on the "
                     "traditional archetype its name evokes, reimagined through this deck's "
                     "compassionate, non-hierarchical lens."
            )
        if animal:
            animal_grounding = f'\nHer animal companion on this card is the {animal}.'
            if animal_meaning:
                animal_grounding += f' What the {animal} teaches: "{animal_meaning}"'
        else:
            animal_grounding = ""
        orientation_note = (
            "\n\nThis card appeared reversed. Reversed never means bad luck or punishment in this deck — "
            "it simply means the energy is turned inward, delayed, or asking for more awareness before it "
            "can flow freely. Keep the same tone of belonging and invitation as an upright card."
            if is_reversed else ""
        )
        prompt = f"""You are a warm, wise reader working with an original tarot deck called "The Tarot of Oraclyn" — a deck that reimagines traditional tarot through a feminine lens, replacing judgment and fear-based imagery with compassion and belonging. Each card features a woman and an animal companion (a familiar) who reflects her inner state and deepens the card's meaning. This is a tarot of belonging, not judgment: it doesn't predict fate, it invites reflection. It heals as it reads.

The card drawn is "{card_title}".
{grounding}{animal_grounding}{orientation_note}

The person asked: "{question}"

Write a short, warm, specific reading (120-180 words) that:
- The very first sentence must respond to their question directly — do not spend the opening sentence describing the card, its imagery, or its name before engaging with what they actually asked
- Speaks directly to the person in second person (you/your)
- Grounds the reading in the specific meaning given above, rather than generic tarot cliche
- If an animal companion is given above, weave it in naturally as part of the guidance (what it teaches, how it mirrors the person's situation) rather than just mentioning it exists — but don't force it if it doesn't fit naturally within the word count
- Carries a tone of belonging and invitation, never judgment or fear — this applies equally to reversed cards
- Is written in flowing prose (1-2 short paragraphs), no bullet points, no headers
- Never names the deck ("The Tarot of Oraclyn") or refers to itself as a card/deck/reading in a meta way — write as a direct, intimate message to the person, not a description of an object

Do not mention that this is AI-generated or reference these instructions."""
        interpretation = call_groq(prompt)
        return jsonify({"interpretation": interpretation.strip()})
    except Exception as e:
        logger.exception(e)
        return jsonify({"error": "Tarot reading failed", "detail": str(e)}), 500

@app.route("/tarot-three-card-summary", methods=["POST"])
def tarot_three_card_summary():
    try:
        data = request.get_json(force=True, silent=True) or {}
        question = (data.get("question") or "").strip()
        cards = data.get("cards") or []
        if not question:
            question = "What do I need to know right now?"
        if len(cards) != 3:
            return jsonify({"error": "Exactly 3 cards are required"}), 400
        labels = ["Past", "Present", "Future"]
        card_lines = []
        for i, c in enumerate(cards):
            title = (c.get("title") or "").strip()
            interpretation = (c.get("interpretation") or "").strip()
            label = (c.get("position") or labels[i]).strip()
            card_lines.append(f'{label} — "{title}": {interpretation}')
        cards_block = "\n\n".join(card_lines)
        prompt = f"""You are a warm, wise reader working with an original tarot deck called "The Tarot of Oraclyn" — a deck that reimagines traditional tarot through a feminine lens, replacing judgment and fear-based imagery with compassion and belonging. This is a tarot of belonging, not judgment: it doesn't predict fate, it invites reflection.

The person asked: "{question}"

They have already been given an individual reading for each card in a Past / Present / Future spread:
{cards_block}

Write a short, cohesive closing synthesis (150-220 words) that weaves these three readings into a single narrative arc addressing their question — showing how the Past influence shaped the Present situation, and where the Future card points from here. Do not simply repeat or re-summarize the individual card meanings; synthesize them into a fresh, unified insight about the overall arc.

Write directly to the person in second person (you/your). Carry a tone of belonging and invitation, never judgment or fear. Write in flowing prose (1-2 short paragraphs), no bullet points, no headers. Never name the deck ("The Tarot of Oraclyn") or refer to itself as a card/deck/reading in a meta way. Do not mention that this is AI-generated or reference these instructions."""
        summary = call_groq(prompt)
        return jsonify({"summary": summary.strip()})
    except Exception as e:
        logger.exception(e)
        return jsonify({"error": "Three-card summary failed", "detail": str(e)}), 500

@app.route("/tarot-celtic-cross-summary", methods=["POST"])
def tarot_celtic_cross_summary():
    try:
        data = request.get_json(force=True, silent=True) or {}
        question = (data.get("question") or "").strip()
        cards = data.get("cards") or []
        if not question:
            question = "What do I need to know right now?"
        if len(cards) != 10:
            return jsonify({"error": "Exactly 10 cards are required"}), 400
        card_lines = []
        for c in cards:
            position = (c.get("position") or "").strip()
            title = (c.get("title") or "").strip()
            orientation = (c.get("orientation") or "upright").strip().lower()
            meaning = (c.get("meaning") or "").strip()
            line = f'{position} — "{title}"'
            if orientation == "reversed":
                line += " (reversed)"
            if meaning:
                line += f': {meaning}'
            card_lines.append(line)
        cards_block = "\n\n".join(card_lines)
        prompt = f"""You are a warm, wise reader working with an original tarot deck called "The Tarot of Oraclyn" — a deck that reimagines traditional tarot through a feminine lens, replacing judgment and fear-based imagery with compassion and belonging. This is a tarot of belonging, not judgment: it doesn't predict fate, it invites reflection.

The person asked: "{question}"

They have drawn a ten-card Celtic Cross spread. Here are the ten positions, in order, each with its card, orientation, and meaning:
{cards_block}

Write this as a single, flowing narrative — a genuine mystical journey of self-discovery, almost an initiation — that moves through these ten positions in the order given, from Present through to the Final Outcome. Treat each position as a stage along this voyage rather than a disconnected fact to list:
- Continually tie the narrative back to their actual question. Don't just describe each card in the abstract — show how each stage speaks to what they specifically asked.
- Build genuine forward motion and arc, the way an experienced reader would talk someone through a full spread out loud — not ten separate mini-paragraphs stitched together, but one continuous voyage with a beginning, a turning point, and an arrival.
- Where reversed cards appear, treat them as the energy turned inward, delayed, or asking for more awareness — never as bad luck or punishment.
- Let the ending (Final Outcome) land with genuine weight — this is the arrival point of the initiation, not just another stage.

Write directly to the person in second person (you/your). Carry a tone of belonging and invitation throughout, never judgment or fear. Write in flowing prose, no bullet points, no headers, no numbered stages. Length approximately 400-500 words — enough room for a real journey across ten stages, but still one continuous piece, not ten mini-sections. Never name the deck ("The Tarot of Oraclyn") or refer to itself as a card/deck/reading in a meta way. Do not mention that this is AI-generated or reference these instructions."""
        summary = call_groq(prompt)
        return jsonify({"summary": summary.strip()})
    except Exception as e:
        logger.exception(e)
        return jsonify({"error": "Celtic Cross summary failed", "detail": str(e)}), 500

PDF_TEMP_DIR = "/tmp/celtic_cross_pdfs"
os.makedirs(PDF_TEMP_DIR, exist_ok=True)

@app.route("/tarot-celtic-cross-pdf", methods=["POST"])
def tarot_celtic_cross_pdf():
    try:
        data = request.get_json(force=True, silent=True) or {}
        question = (data.get("question") or "").strip() or "What do I need to know right now?"
        cards = data.get("cards") or []
        summary = (data.get("summary") or "").strip()
        if len(cards) != 10:
            return jsonify({"error": "Exactly 10 cards are required"}), 400
        if not summary:
            return jsonify({"error": "summary is required"}), 400
        t0 = time.time()
        cards_with_embedded_images = prefetch_card_images(cards)
        t1 = time.time()
        logger.info("Celtic Cross PDF: image prefetch took %.2fs", t1 - t0)
        html = render_celtic_cross_pdf_html(question, cards_with_embedded_images, summary)
        t2 = time.time()
        logger.info("Celtic Cross PDF: HTML build took %.2fs", t2 - t1)
        pdf_bytes = weasyprint.HTML(string=html).write_pdf()
        t3 = time.time()
        logger.info("Celtic Cross PDF: weasyprint render took %.2fs", t3 - t2)
        file_id = uuid.uuid4().hex[:16]
        file_path = os.path.join(PDF_TEMP_DIR, f"{file_id}.pdf")
        with open(file_path, "wb") as f:
            f.write(pdf_bytes)
        t4 = time.time()
        logger.info("Celtic Cross PDF: file write took %.2fs (total %.2fs)", t4 - t3, t4 - t0)
        pdf_url = f"/tarot-celtic-cross-pdf-file/{file_id}"
        return jsonify({"pdf_url": pdf_url})
    except Exception as e:
        logger.exception(e)
        return jsonify({"error": "PDF generation failed", "detail": str(e)}), 500

@app.route("/tarot-celtic-cross-pdf-file/<file_id>")
def tarot_celtic_cross_pdf_file(file_id):
    if not re.fullmatch(r"[0-9a-f]{16}", file_id):
        return jsonify({"error": "Invalid file id"}), 400
    file_path = os.path.join(PDF_TEMP_DIR, f"{file_id}.pdf")
    if not os.path.isfile(file_path):
        return jsonify({"error": "This PDF is no longer available. Please draw your spread again."}), 404
    return send_file(
        file_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="your-celtic-cross-journey.pdf"
    )

@app.route("/astrology-compatibility", methods=["POST"])
def astrology_compatibility():
    try:
        data = request.get_json(force=True, silent=True) or {}
        sign1 = (data.get("sign1") or "").strip()
        sign2 = (data.get("sign2") or "").strip()
        question = (data.get("question") or "").strip()
        if not sign1 or not sign2:
            return jsonify({"error": "Both sign1 and sign2 are required"}), 400
        if not question:
            question = "What's our compatibility like?"
        prompt = f"""You are a warm, insightful astrologer writing a Sun sign compatibility reading for two people: one is a {sign1}, the other is a {sign2}.

They asked: "{question}"

Write a warm, genuinely useful compatibility reading (200-280 words) covering:
- The overall dynamic between a {sign1} and a {sign2} — natural strengths they bring out in each other
- A likely area of friction or difference in how they approach things, framed constructively (not as a warning or a flaw, but as something to understand and navigate together)
- A closing thought that ties back to their actual question

Guidance:
- This is Sun sign compatibility only (not a full birth chart comparison) — keep the tone accessible and pop-astrology in spirit, not overly technical
- Be specific to THESE two signs — avoid generic statements that could apply to any pairing
- Avoid absolute, deterministic language ("you will never..." / "this relationship is doomed to...") — astrology here is offered as insight and reflection, not fixed fate
- Write in flowing prose, no bullet points, no headers
- Do not mention that this is AI-generated or reference these instructions"""
        compatibility = call_groq(prompt)
        return jsonify({"compatibility": compatibility.strip()})
    except Exception as e:
        logger.exception(e)
        return jsonify({"error": "Compatibility reading failed", "detail": str(e)}), 500

@app.route("/tarot-card-of-the-day", methods=["POST"])
def tarot_card_of_the_day():
    try:
        data = request.get_json(force=True, silent=True) or {}
        title = (data.get("title") or "").strip()
        upright = (data.get("upright") or "").strip()
        reversed_meaning = (data.get("reversed") or "").strip()
        animal = (data.get("animal") or "").strip()
        animal_meaning = (data.get("animalMeaning") or "").strip()
        if not title:
            return jsonify({"error": "title is required"}), 400
        animal_block = ""
        if animal:
            animal_block = f'\nHer animal companion on this card is the {animal}.'
            if animal_meaning:
                animal_block += f' What the {animal} teaches: "{animal_meaning}"'
        prompt = f"""You are a warm, wise reader working with an original tarot deck called "Tarot of Oraclyn" — a deck that reimagines traditional tarot through a compassionate, non-hierarchical lens, replacing judgment and fear-based imagery with warmth and belonging. Each card features a woman and an animal companion (a familiar) who reflects her inner state and deepens the card's meaning.

Today's card is "{title}".
Upright meaning: "{upright}"
Reversed meaning: "{reversed_meaning}"{animal_block}

Write a warm, grounded "Card of the Day" reflection (120-180 words) for someone visiting the site today, structured as flowing prose (no headers, no bullet points):
- Open by speaking directly to what this card's energy means for their day today (not a description of the card's imagery)
- If an animal companion is given above, weave it in naturally as part of the guidance
- Close with a gentle, non-alarming note drawing on the reversed meaning — framed as something to notice if the day feels resistant, not a warning

Write in second person (you/your). Carry a tone of belonging and invitation, never judgment or fear. Never name the deck ("Tarot of Oraclyn") or refer to itself as a card/deck/reading in a meta way. Do not mention that this is AI-generated or reference these instructions."""
        reflection = call_groq(prompt)
        return jsonify({"reflection": reflection.strip()})
    except Exception as e:
        logger.exception(e)
        return jsonify({"error": "Card of the day reflection failed", "detail": str(e)}), 500

@app.route("/synastry-reading", methods=["POST"])
def synastry_reading():
    try:
        data = request.get_json(force=True, silent=True) or {}

        name1 = (data.get("name1") or "Person A").strip()
        year1 = int(data.get("year1"))
        month1 = int(data.get("month1"))
        day1 = int(data.get("day1"))
        hour1 = int(data.get("hour1", 12))
        minute1 = int(data.get("minute1", 0))
        city1 = (data.get("city1") or "").strip()
        country1 = (data.get("country1") or "").strip()

        name2 = (data.get("name2") or "Person B").strip()
        year2 = int(data.get("year2"))
        month2 = int(data.get("month2"))
        day2 = int(data.get("day2"))
        hour2 = int(data.get("hour2", 12))
        minute2 = int(data.get("minute2", 0))
        city2 = (data.get("city2") or "").strip()
        country2 = (data.get("country2") or "").strip()

        if not all([city1, country1, city2, country2]):
            return jsonify({"error": "Both people's city and country are required"}), 400

        subject1 = build_subject(name1, year1, month1, day1, hour1, minute1, city1, country1)
        subject2 = build_subject(name2, year2, month2, day2, hour2, minute2, city2, country2)

        def extract_points(subject):
            return {
                "Sun": subject.sun.sign,
                "Moon": subject.moon.sign,
                "Mercury": subject.mercury.sign,
                "Venus": subject.venus.sign,
                "Mars": subject.mars.sign,
                "Jupiter": subject.jupiter.sign,
                "Saturn": subject.saturn.sign,
                "Uranus": subject.uranus.sign,
                "Neptune": subject.neptune.sign,
                "Pluto": subject.pluto.sign,
                "Ascendant": subject.first_house.sign,
                "Chiron": subject.chiron.sign,
                "Lilith": subject.mean_lilith.sign,
                "North Node": subject.mean_north_lunar_node.sign,
                "South Node": subject.mean_south_lunar_node.sign,
                "Part of Fortune": subject.pars_fortunae.sign,
            }

        points1 = extract_points(subject1)
        points2 = extract_points(subject2)

        chart_lines_1 = "\n".join(f"- {k}: {v}" for k, v in points1.items())
        chart_lines_2 = "\n".join(f"- {k}: {v}" for k, v in points2.items())

        prompt = f"""You are an experienced, warm and insightful astrologer writing a full relationship compatibility (synastry) reading for two people.

{name1}'s chart:
{chart_lines_1}

{name2}'s chart:
{chart_lines_2}

Structure your response using EXACTLY these section headings, in this exact order, each on its own line starting with "## " (two hash symbols and a space), with the section's writing directly beneath it. Do not add, remove, rename, or reorder headings. Do not use any other markdown (no bullet points, no bold, no numbered lists) — just plain flowing paragraphs under each heading:
## Overview
## Sun & Moon Dynamic
## Venus & Mars: Attraction and Friction
## Mercury: How You Communicate
## Ascendant: First Impressions
## Chiron: Shared Wounds, Shared Healing
## Lilith: The Instinctual Undercurrent
## The Lunar Nodes: Where This Connection Is Pulling You
## Part of Fortune: Where Ease Flows Between You
## Growth Edge
## Closing Thought

Guidance for each section:
- Overview: a brief, engaging 2-3 sentence introduction to the overall energy between these two charts.
- Sun & Moon Dynamic: how their core identities and emotional needs interact.
- Venus & Mars: attraction, romantic style, and where friction might show up — framed constructively, not as a warning.
- Mercury: how they talk to and understand each other.
- Ascendant: how they come across to each other day-to-day.
- Chiron: where their core wounds might mirror or trigger each other, and how facing this together can be healing rather than painful.
- Lilith: the raw, instinctual, unfiltered parts of each person this connection brings out — described with curiosity, not judgment.
- The Lunar Nodes: comparing North/South Node placements — what old patterns this relationship might surface, and what growth it's pointing toward for both people.
- Part of Fortune: a short, warm note on where natural ease and good luck show up between them.
- Growth Edge: one honest, constructive challenge area — an invitation, not a verdict.
- Closing Thought: a warm, encouraging closing paragraph tying the themes together.

Total length approximately 900-1200 words across all sections. Write directly about {name1} and {name2} by name (not just "you") so it reads as being about their specific connection. Be warm, insightful and specific — avoid generic statements that could apply to any pairing. Keep an emotionally intelligent, non-fatalistic tone throughout, especially for the Chiron/Lilith/Nodes sections — these are invitations, not verdicts. Avoid absolute, deterministic language ("you will never..." / "this relationship is doomed to...")."""

        interpretation = call_groq(prompt)
        html_content = format_sectioned_interpretation(interpretation)

        return jsonify({
            "interpretation_html": html_content,
            "raw": interpretation.strip()
        })

    except Exception as e:
        logger.exception(e)
        return jsonify({"error": "Synastry reading failed", "detail": str(e)}), 500

SYNASTRY_PDF_TEMP_DIR = "/tmp/synastry_pdfs"
os.makedirs(SYNASTRY_PDF_TEMP_DIR, exist_ok=True)

@app.route("/synastry-pdf", methods=["POST"])
def synastry_pdf():
    try:
        data = request.get_json(force=True, silent=True) or {}

        name1 = (data.get("name1") or "Person A").strip()
        city1 = (data.get("city1") or "").strip()
        country1 = (data.get("country1") or "").strip()

        name2 = (data.get("name2") or "Person B").strip()
        city2 = (data.get("city2") or "").strip()
        country2 = (data.get("country2") or "").strip()

        html_content = (data.get("interpretation_html") or "").strip()
        if not html_content:
            return jsonify({"error": "interpretation_html is required"}), 400

        html = render_synastry_pdf_html(name1, city1, country1, name2, city2, country2, html_content)
        pdf_bytes = weasyprint.HTML(string=html).write_pdf()

        file_id = uuid.uuid4().hex[:16]
        file_path = os.path.join(SYNASTRY_PDF_TEMP_DIR, f"{file_id}.pdf")
        with open(file_path, "wb") as f:
            f.write(pdf_bytes)

        pdf_url = f"/synastry-pdf-file/{file_id}"
        return jsonify({"pdf_url": pdf_url})

    except Exception as e:
        logger.exception(e)
        return jsonify({"error": "PDF generation failed", "detail": str(e)}), 500

@app.route("/synastry-pdf-file/<file_id>")
def synastry_pdf_file(file_id):
    if not re.fullmatch(r"[0-9a-f]{16}", file_id):
        return jsonify({"error": "Invalid file id"}), 400
    file_path = os.path.join(SYNASTRY_PDF_TEMP_DIR, f"{file_id}.pdf")
    if not os.path.isfile(file_path):
        return jsonify({"error": "This PDF is no longer available. Please generate your report again."}), 404
    return send_file(
        file_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="full-compatibility-report.pdf"
    )

if __name__ == "__main__":
    app.run(debug=True)

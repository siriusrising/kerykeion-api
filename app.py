@app.route("/chart-page")
def chart_page():

    try:

        year = int(request.args["year"])
        month = int(request.args["month"])
        day = int(request.args["day"])
        hour = int(request.args.get("hour", 12))
        minute = int(request.args.get("minute", 0))

        city = request.args["city"]
        country = request.args["country"]

        subject = AstrologicalSubjectFactory.from_birth_data(
            name="Chart",
            year=year,
            month=month,
            day=day,
            hour=hour,
            minute=minute,
            city=city,
            nation=country,
            geonames_username=GEONAMES_USERNAME,
            online=True
        )

        chart_data = ChartDataFactory.create_natal_chart_data(subject)
        drawer = ChartDrawer(chart_data=chart_data)

        svg = drawer.generate_svg_string()

        html = f"""
<!DOCTYPE html>
<html>
<head>

<meta charset="utf-8">

<style>

html,body{{
    margin:0;
    padding:0;
    width:100%;
    height:100%;
    overflow-x:hidden;
    background:white;
}}

svg{{
    display:block;
    width:100%;
    height:auto;
}}

</style>

</head>

<body>

{svg}

</body>

</html>
"""

        return Response(html, mimetype="text/html")

    except Exception as e:

        logger.exception(e)

        return jsonify({{
            "error":"Chart generation failed",
            "detail":str(e)
        }}),500

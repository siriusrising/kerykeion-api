# Add this route to app.py, right before: if __name__ == "__main__":
# Uses your existing call_groq() helper — no new Groq client/import needed,
# matches the exact pattern of your other routes (tarot_reading, astrology_compatibility, etc.)

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

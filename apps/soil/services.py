import json

from google import genai
from google.genai import types
from django.conf import settings

_PROMPT_TEMPLATE = """
You are an expert agricultural soil scientist. Analyze this soil photograph carefully.

Respond in {language}.

Return ONLY a valid JSON object — no markdown, no explanation, no code fences — with exactly these fields:

{{
  "is_soil_photo": <true if this image is a clear, close-up photo of exposed soil/ground/dirt that can be analyzed; false if it mainly shows plants, crops, leaves, buildings, sky, people, or anything else that isn't exposed soil>,
  "soil_type": "<one of: Clay, Sandy, Loam, Silt, Laterite, Black Cotton, Alluvial, Unknown>",
  "color": "<color description, e.g. Dark Brown, Reddish Brown, Light Yellow, Grey>",
  "texture": "<Fine, Medium, or Coarse>",
  "moisture_appearance": "<Dry, Moist, or Wet>",
  "organic_matter": "<Low, Medium, or High — inferred from color darkness and structure>",
  "ph_estimate": "<Acidic, Neutral, or Alkaline — inferred from color and soil type>",
  "fertility_estimate": "<Low, Medium, or High>",
  "visible_issues": ["<e.g. compaction, erosion, waterlogging, nutrient deficiency — empty list if none>"],
  "soil_amendments": ["<recommended amendment, e.g. add compost, lime, sand — empty list if none needed>"],
  "confidence": "<Low, Medium, or High — how confident you are given image quality>"
}}
"""

_LANGUAGE_NAMES = {
    "en": "English",
    "fr": "French",
    "sw": "Swahili",
    "ha": "Hausa",
    "yo": "Yoruba",
    "ig": "Igbo",
    "am": "Amharic",
    "zu": "Zulu",
    "xh": "Xhosa",
    "tw": "Twi",
    "wo": "Wolof",
    "ln": "Lingala",
    "sn": "Shona",
    "dyu": "Dioula",
    "bci": "Baoulé",
    "bm": "Bambara",
    "ff": "Fulani",
}


class NotSoilImageError(Exception):
    """Raised when the uploaded image doesn't show soil that can be analyzed."""


def analyze_soil_image(image_bytes: bytes, language: str = "en") -> dict:
    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    language_name = _LANGUAGE_NAMES.get(language, "English")
    prompt = _PROMPT_TEMPLATE.format(language=language_name)

    image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")

    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=[image_part, prompt],
    )

    text = response.text.strip()

    # Strip markdown code fences if Gemini wraps the JSON
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1])

    result = json.loads(text)

    if not result.pop("is_soil_photo", True):
        raise NotSoilImageError(
            "This doesn't look like a photo of soil. Please take a close-up "
            "photo of the exposed ground/dirt, not plants, crops, or the wider field."
        )

    return result

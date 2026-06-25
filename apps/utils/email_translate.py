import logging

from django.conf import settings
from google import genai

logger = logging.getLogger(__name__)

_LANGUAGE_NAMES = {
    "en": "English", "fr": "French", "sw": "Swahili", "ha": "Hausa",
    "yo": "Yoruba", "ig": "Igbo", "am": "Amharic", "zu": "Zulu",
    "xh": "Xhosa", "tw": "Twi", "wo": "Wolof", "ln": "Lingala",
    "sn": "Shona", "dyu": "Dioula", "bci": "Baoulé", "bm": "Bambara",
    "ff": "Fulani",
}


def translate_email_content(text: str, language: str) -> str:
    """Translate email text to the target language using Gemini. Returns original on failure."""
    if language == "en" or not text.strip():
        return text
    language_name = _LANGUAGE_NAMES.get(language, "English")
    try:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=(
                f"Translate the following email text to {language_name}. "
                f"Keep the exact format, line breaks, and structure. "
                f"Do not translate email addresses, passwords, OTP codes, numbers, or proper nouns like 'EasyAgric'. "
                f"Return only the translated text, nothing else.\n\n{text}"
            ),
        )
        return response.text.strip()
    except Exception:
        logger.exception("Failed to translate email to %s — sending in English", language)
        return text

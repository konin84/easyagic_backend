import logging
import sys

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_GT_API_URL = "https://translation.googleapis.com/language/translate/v2"

# Google Translate language codes for our supported languages.
# Most match ISO 639-1 directly; a few differ from our internal codes.
_GT_CODE_MAP = {
    "en": "en", "fr": "fr", "sw": "sw", "ha": "ha",
    "yo": "yo", "ig": "ig", "am": "am", "zu": "zu",
    "xh": "xh", "tw": "tw", "wo": "wo", "ln": "ln",
    "sn": "sn", "dyu": "dyu", "bci": "bci", "bm": "bm",
    "ff": "ff",
}


def translate_email_content(text: str, language: str, is_html: bool = False) -> str:
    """
    Translate email content to the target language using Google Cloud Translation API.
    When is_html=True, HTML tags are preserved automatically by the API.
    Returns the original text if language is English or translation fails.
    """
    if language == "en" or not text.strip():
        return text

    api_key = getattr(settings, "GOOGLE_TRANSLATE_API_KEY", "")
    if not api_key:
        logger.warning("GOOGLE_TRANSLATE_API_KEY not set — email will be sent in English")
        return text

    gt_code = _GT_CODE_MAP.get(language)
    if not gt_code:
        return text

    try:
        response = requests.post(
            _GT_API_URL,
            params={"key": api_key},
            json={
                "q": text,
                "source": "en",
                "target": gt_code,
                "format": "html" if is_html else "text",
            },
            timeout=15,
        )
        response.raise_for_status()
        return response.json()["data"]["translations"][0]["translatedText"]
    except Exception as exc:
        print(
            f"[email_translate] WARNING: Google Translate to '{language}' failed: {exc}",
            file=sys.stderr,
        )
        logger.warning("Google Translate to '%s' failed: %s", language, exc)
        return text

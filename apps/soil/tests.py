from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from .services import NotSoilImageError, analyze_soil_image

VALID_JSON = (
    '{"is_soil_photo": true, "soil_type": "Loam", "color": "Dark Brown",'
    ' "texture": "Fine", "moisture_appearance": "Moist", "organic_matter": "High",'
    ' "ph_estimate": "Neutral", "fertility_estimate": "High",'
    ' "visible_issues": [], "soil_amendments": [], "confidence": "High"}'
)


def fake_client(text):
    client = MagicMock()
    client.models.generate_content.return_value = MagicMock(text=text)
    return client


class SoilAnalysisServiceTests(TestCase):
    def call(self, text, **kwargs):
        client = fake_client(text)
        with patch("apps.soil.services.genai.Client", return_value=client):
            result = analyze_soil_image(b"fake-bytes", **kwargs)
        return result, client.models.generate_content.call_args.kwargs

    @override_settings(GEMINI_MODEL="gemini-3.6-flash")
    def test_uses_the_model_from_settings(self):
        _, call = self.call(VALID_JSON)
        self.assertEqual(call["model"], "gemini-3.6-flash")

    @override_settings(GEMINI_MODEL="gemini-flash-latest")
    def test_model_is_swappable_without_touching_code(self):
        """A retired model must be fixable by changing an env var, not a deploy."""
        _, call = self.call(VALID_JSON)
        self.assertEqual(call["model"], "gemini-flash-latest")

    def test_returns_the_parsed_analysis_without_the_gate_flag(self):
        result, _ = self.call(VALID_JSON)
        self.assertEqual(result["soil_type"], "Loam")
        self.assertNotIn("is_soil_photo", result)

    def test_markdown_fenced_json_is_still_parsed(self):
        result, _ = self.call(f"```json\n{VALID_JSON}\n```")
        self.assertEqual(result["soil_type"], "Loam")

    def test_non_soil_photo_is_rejected(self):
        with self.assertRaises(NotSoilImageError):
            self.call(VALID_JSON.replace('"is_soil_photo": true', '"is_soil_photo": false'))

    def test_prompt_is_written_in_the_users_language(self):
        _, call = self.call(VALID_JSON, language="sw")
        prompt = call["contents"][1]
        self.assertIn("Respond in Swahili", prompt)

    def test_unknown_language_falls_back_to_english(self):
        _, call = self.call(VALID_JSON, language="zz")
        self.assertIn("Respond in English", call["contents"][1])

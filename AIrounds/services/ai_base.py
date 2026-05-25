from django.conf import settings
from google import genai
from google.genai import types
import logging
import json

logger = logging.getLogger("ai_rounds.ai_base")


class AIBaseService:
    """Handles low-level AI model configuration and client management."""

    _client = None
    MODEL_NAME = "gemini-2.5-flash"

    @classmethod
    def get_client(cls):
        if cls._client is None:
            api_key = getattr(settings, "GEMINI_API_KEY", None)
            if not api_key:
                logger.error("GEMINI_API_KEY not found in settings.")
                raise ValueError("GEMINI_API_KEY not configured.")
            cls._client = genai.Client(api_key=api_key)
        return cls._client

    @classmethod
    def generate_content(cls, prompt, system_instruction, temperature=0.7, response_schema=None):
        client = cls.get_client()
        try:
            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=temperature,
                response_mime_type="application/json",
                response_schema=response_schema,
            )

            response = client.models.generate_content(
                model=cls.MODEL_NAME,
                contents=[prompt],
                config=config,
            )

            raw_text = response.text
            if not raw_text:
                logger.error("Gemini returned empty response.")
                raise ValueError("AI returned an empty response.")

            # Strip markdown code fences if the model wraps JSON in them
            cleaned = raw_text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]  # drop first line
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3].strip()

            return cleaned

        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            raise ValueError(f"AI Service Error: {str(e)}")

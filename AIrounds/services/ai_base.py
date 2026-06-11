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
    def get_model_for_company(cls, company):
        if not company:
            return cls.MODEL_NAME
        try:
            from organization.models import Organization
            from agentsettings.models import AgentSettings
            
            organization = Organization.objects.filter(company=company).first()
            if organization:
                settings_obj = AgentSettings.objects.filter(organization=organization).first()
                if settings_obj and settings_obj.llm_model:
                    return settings_obj.llm_model
        except Exception as e:
            logger.error(f"Error resolving model for company {company}: {e}")
        return cls.MODEL_NAME

    @classmethod
    def generate_content(cls, prompt, system_instruction, temperature=0.7, response_schema=None, model_name="gemini-2.5-flash"):
        if model_name in ("kimi", "Kimi-K2.6"):
            from AI.services import AIService
            full_prompt = f"{system_instruction}\n\nUSER PROMPT:\n{prompt}"
            raw_text = AIService.call_kimi_api(full_prompt)
        elif model_name in ("grok", "grok-4-20-non-reasoning", "grok-4.20-non-reasoning"):
            from AI.services import AIService
            full_prompt = f"{system_instruction}\n\nUSER PROMPT:\n{prompt}"
            raw_text = AIService.call_grok_api(full_prompt)
        elif model_name in ("grok-4.1-non-reasoning", "grok-4-1-fast-non-reasoning"):
            from AI.services import AIService
            full_prompt = f"{system_instruction}\n\nUSER PROMPT:\n{prompt}"
            raw_text = AIService.call_grok_4_1_api(full_prompt)
        else:
            client = cls.get_client()
            try:
                gemini_model = model_name if model_name in ("gemini-2.5-flash", "gemini-2.5-flash-lite") else cls.MODEL_NAME
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=temperature,
                    response_mime_type="application/json",
                    response_schema=response_schema,
                )

                response = client.models.generate_content(
                    model=gemini_model,
                    contents=[prompt],
                    config=config,
                )

                raw_text = response.text
            except Exception as e:
                logger.error(f"Gemini API call failed: {e}")
                raise ValueError(f"AI Service Error: {str(e)}")

        if not raw_text:
            logger.error("AI returned empty response.")
            raise ValueError("AI returned an empty response.")

        # Strip markdown code fences if the model wraps JSON in them
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]  # drop first line
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()

        return cleaned

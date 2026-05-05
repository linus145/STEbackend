import requests
import re
import time
import logging

from google import genai
from google.genai import types
from django.conf import settings

logger = logging.getLogger("ai.service")

# Model pipeline: (model_id, max_retries)
# Primary: gemini-2.5-flash (more capable, handles complex/large PDFs)
# Fallback: gemini-2.5-flash-lite (faster, lighter)
MODEL_PIPELINE = [
    ("gemini-2.5-flash", 3),
    ("gemini-2.5-flash-lite", 2),
]


class AIServiceError(Exception):
    """Raised when all AI models fail."""

    pass


class AIService:
    # ─── Google Drive Helpers ──────────────────────────────────────────────

    @staticmethod
    def _extract_gdrive_file_id(url):
        """Extracts Google Drive file ID from various URL formats."""
        patterns = [
            r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)",
            r"drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)",
            r"drive\.google\.com/uc\?.*id=([a-zA-Z0-9_-]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def _download_from_gdrive(file_id):
        """Downloads from Google Drive. Returns (bytes, error_reason)."""
        session = requests.Session()
        url = f"https://drive.google.com/uc?export=download&id={file_id}"
        response = session.get(url, timeout=30)

        # Handle virus scan confirmation cookie
        for key, value in response.cookies.items():
            if key.startswith("download_warning"):
                url = f"https://drive.google.com/uc?export=download&confirm={value}&id={file_id}"
                response = session.get(url, timeout=30)
                break

        content_type = response.headers.get("Content-Type", "")
        if response.status_code == 200 and "text/html" not in content_type.lower():
            print(
                f"[AI] ✅ Downloaded from Google Drive: {file_id} ({len(response.content)} bytes)"
            )
            return response.content, None

        if "text/html" in content_type.lower():
            print(f"[AI] ❌ Google Drive file is restricted: {file_id}")
            return (
                None,
                "Resume file is restricted on Google Drive. The file sharing must be set to 'Anyone with the link'.",
            )

        print(
            f"[AI] ❌ Google Drive download failed: {file_id} (HTTP {response.status_code})"
        )
        return None, f"Google Drive download failed (HTTP {response.status_code})"

    # ─── PDF Download ─────────────────────────────────────────────────────

    @staticmethod
    def download_pdf(pdf_url):
        """Downloads a PDF from a URL. Returns (bytes, error_reason)."""
        try:
            file_id = AIService._extract_gdrive_file_id(pdf_url)
            if file_id:
                print(f"[AI] Detected Google Drive file: {file_id}")
                return AIService._download_from_gdrive(file_id)

            if "dropbox.com" in pdf_url:
                dl_url = pdf_url.replace("?dl=0", "?dl=1")
                resp = requests.get(dl_url, timeout=30)
                if resp.status_code == 200:
                    return resp.content, None
                return None, f"Dropbox download failed (HTTP {resp.status_code})"

            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(
                pdf_url, headers=headers, timeout=30, allow_redirects=True
            )
            if resp.status_code == 200:
                return resp.content, None

            return None, f"Download failed (HTTP {resp.status_code})"

        except requests.exceptions.Timeout:
            return None, "Download timed out — file server too slow"
        except Exception as e:
            return None, f"Download error: {str(e)}"

    # ─── Gemini AI Analysis (Inline Bytes — No Upload) ────────────────────

    @staticmethod
    def analyze_resume(job_title, job_description, resume_url):
        """
        Analyzes a resume against a job description using Gemini.
        Sends PDF bytes inline (no file upload) for maximum speed.
        Returns (score, analysis_text) or (None, error_message).
        """
        api_key = getattr(settings, "GEMINI_API_KEY", None)
        if not api_key:
            return None, "AI service not configured"

        # 1. Download the PDF
        pdf_bytes, download_error = AIService.download_pdf(resume_url)
        if not pdf_bytes:
            return None, download_error or "Could not download resume"

        try:
            # 2. Initialize Gemini Client
            client = genai.Client(api_key=api_key)

            # 3. Create inline PDF part (NO file upload needed)
            pdf_part = types.Part.from_bytes(
                data=pdf_bytes, mime_type="application/pdf"
            )
            print(f"[AI] Inline PDF ready ({len(pdf_bytes)} bytes) — no upload needed")

            # 4. Build prompt — detailed analysis (~1000 chars)
            prompt = f"""You are an ATS (Applicant Tracking System) expert recruiter.
Analyze this PDF resume against the job below.

JOB: {job_title}
DESCRIPTION: {job_description}

Return EXACTLY this format:
SCORE: [0-100]
ANALYSIS:
- Experience: [Provide a detailed 1-2 sentence overview of relevant experience, specific roles, and tenure]
- Key Skills: [List 5-8 top matching skills for this role, highlighting specific technical proficiencies]
- Strengths: [Provide a 2-3 sentence paragraph on what makes this candidate a strong fit, citing specific achievements]
- Gaps: [Identify specific missing qualifications or areas for improvement in 1-2 sentences]
- Verdict: [A comprehensive overall recommendation and reasoning]

Provide a deep, multi-line analysis for each section. Ensure the full ANALYSIS is between 800 and 1200 characters."""

            # 5. Call Gemini with model pipeline (no upload/cleanup needed)
            last_error = None
            for model_name, max_retries in MODEL_PIPELINE:
                for attempt in range(1, max_retries + 1):
                    try:
                        print(
                            f"[AI] Trying {model_name} (attempt {attempt}/{max_retries})"
                        )

                        response = client.models.generate_content(
                            model=model_name,
                            contents=[pdf_part, prompt],
                            config=types.GenerateContentConfig(
                                max_output_tokens=8000,
                                temperature=0.3,
                            ),
                        )

                        content = response.text
                        if content:
                            score, analysis = AIService._parse_response(content)
                            print(f"[AI] ✅ {model_name}: score={score}")
                            return score, analysis

                        last_error = "Empty response"
                        print(f"[AI] ⚠️ {model_name}: empty response")
                        time.sleep(1)

                    except Exception as e:
                        last_error = str(e)
                        print(f"[AI] ⚠️ {model_name} error: {last_error}")
                        if (
                            "block" in last_error.lower()
                            or "safety" in last_error.lower()
                        ):
                            break
                        time.sleep(1 * attempt)

            return 0, f"AI analysis failed: {last_error}"

        except Exception as e:
            print(f"[AI] Analysis error: {e}")
            return 0, f"AI analysis failed: {str(e)}"

    # ─── Response Parser ──────────────────────────────────────────────────

    @staticmethod
    def _parse_response(content):
        """Parses SCORE: and ANALYSIS: from Gemini response."""
        score = 0
        analysis = ""

        for line in content.split("\n"):
            line_stripped = line.strip()
            if line_stripped.upper().startswith("SCORE:"):
                try:
                    score_text = line_stripped.split(":", 1)[1].strip()
                    # Handle "85/100" or "85%" formats
                    score_text = score_text.replace("%", "").split("/")[0].strip()
                    score = int(score_text)
                    score = max(0, min(100, score))  # Clamp 0-100
                except (ValueError, IndexError):
                    pass
            elif line_stripped.upper().startswith("ANALYSIS:"):
                # Capture everything after ANALYSIS: including multi-line content
                analysis_start = content.upper().find("ANALYSIS:")
                if analysis_start != -1:
                    analysis = content[analysis_start + 9 :].strip()

        if not analysis:
            analysis = content  # Use full response as fallback

        # Hard-cap at 1000 chars for detailed display
        if len(analysis) > 20000:
            analysis = analysis[:19997] + "..."

        return score, analysis

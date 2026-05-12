import json
import logging
import re
import time

import requests
from django.conf import settings
from google import genai
from google.genai import types

logger = logging.getLogger("ai.service")

# Model pipeline: (model_id, max_retries)
# Optimized for SPEED on free tier:
# Primary: gemini-2.5-flash-lite — fastest, highest free-tier limits
# Fallback: gemini-2.5-flash — more capable but slower
MODEL_PIPELINE = [
    ("gemini-2.5-flash-lite", 2),
    ("gemini-2.5-flash", 2),
]

# Reusable client singleton (avoids re-init overhead per call)
_client_cache = {}


def _get_client(api_key):
    """Returns a cached Gemini client to avoid repeated initialization."""
    if api_key not in _client_cache:
        _client_cache[api_key] = genai.Client(api_key=api_key)
    return _client_cache[api_key]


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
        Analyzes a resume against a job description using the Agentic ATS Architecture.
        Returns (score, analysis_json_or_text).
        """
        api_key = getattr(settings, "GEMINI_API_KEY", None)
        if not api_key:
            return None, "AI service not configured"

        # 1. Download the PDF
        pdf_bytes, download_error = AIService.download_pdf(resume_url)
        if not pdf_bytes:
            return None, download_error or "Could not download resume"

        try:
            # 2. Get cached Gemini Client (avoids re-initialization overhead)
            client = _get_client(api_key)

            # 3. Create inline PDF part
            pdf_part = types.Part.from_bytes(
                data=pdf_bytes, mime_type="application/pdf"
            )

            # 4. Build the OPTIMIZED Prompt (calibrated scoring)
            prompt = f"""You are an expert ATS screening engine. Analyze this resume against the job and produce balanced, realistic scores.

JOB TITLE: {job_title}
JOB DESCRIPTION: {job_description[:2000]}

SCORING GUIDE (each sub-score is 0-100, then weighted):
- Skills Match (25%): How well do candidate's skills align with the job requirements?
- Project Relevance (20%): Are their projects complex, relevant, and well-described?
- Experience Match (15%): Does their work history align with the role's seniority and domain?
- Semantic Understanding (10%): Do they show deep understanding of the problem space?
- Startup Compatibility (10%): Can they adapt, wear multiple hats, move fast?
- Trust & Credibility (10%): Is the resume well-structured, consistent, detailed, and professional? A well-written resume with specific dates, metrics, and clear descriptions should score 60-90. Only flag low trust (below 30) if there are clear contradictions or red flags.
- Communication (5%): Quality of writing, clarity, and structured thinking.
- Growth Signals (5%): Evidence of continuous learning, side projects, certifications.

IMPORTANT: The final match_score should be the weighted sum. The trust_score in recruiter_view should reflect resume quality and consistency (typically 50-90 for normal resumes). Only score trust below 30 if there are CLEAR red flags like contradictory dates or fabricated claims.

Return ONLY this JSON:
{{
  "intelligence": {{
    "candidate_info": {{ "full_name": "", "email": "", "location": "" }},
    "summary": {{ "primary_role": "", "specialization": "", "years_of_experience": 0 }},
    "skills": {{ "frontend": [], "backend": [], "database": [], "devops": [], "ai": [], "soft": [] }},
    "experience": [ {{ "company": "", "role": "", "duration": "", "technologies": [] }} ],
    "projects": [ {{ "name": "", "complexity_score": 0 }} ],
    "startup_intel": {{ "startup_experience": false, "founder_mindset": false, "ownership_score": 0 }},
    "trust_signals": {{ "resume_ai_probability": 0, "consistency_score": 0 }}
  }},
  "recruiter_view": {{
    "match_score": 0,
    "strengths": [],
    "concerns": [],
    "red_flags": [],
    "startup_fit": "Low/Medium/High",
    "trust_score": 0,
    "recommended_action": "",
    "explanation": "",
    "interview_questions": []
  }}
}}"""

            # 5. Call Gemini — optimized for speed and reliability
            last_error = None
            for model_name, max_retries in MODEL_PIPELINE:
                for attempt in range(1, max_retries + 1):
                    try:
                        t0 = time.time()
                        print(f"[AI] ⚡ Calling {model_name} (Attempt {attempt})...")
                        
                        response = client.models.generate_content(
                            model=model_name,
                            contents=[pdf_part, prompt],
                            config=types.GenerateContentConfig(
                                max_output_tokens=3000, # Reduced for speed
                                temperature=0.1,
                                response_mime_type="application/json",
                            ),
                        )

                        if response and response.text:
                            content = response.text
                            elapsed = time.time() - t0
                            print(f"[AI] ✅ {model_name} response received in {elapsed:.1f}s")
                            
                            score, analysis = AIService._parse_response(content)
                            if score is not None:
                                return score, analysis
                            else:
                                last_error = "Parser returned None"
                        else:
                            last_error = "Empty response from Gemini"
                            
                    except Exception as e:
                        last_error = str(e)
                        print(f"[AI] ⚠️ {model_name} failed: {last_error}")
                        # Exponential backoff for rate limits
                        if "429" in last_error or "Quota" in last_error:
                            sleep_time = 2 * attempt
                            print(f"[AI] Rate limit hit. Sleeping for {sleep_time}s...")
                            time.sleep(sleep_time)
                        else:
                            time.sleep(1) # General small wait

            return 0, f"AI analysis failed after all retries. Last error: {last_error}"

        except Exception as e:
            print(f"[AI] Analysis error: {e}")
            return 0, f"AI analysis failed: {str(e)}"

    # ─── Response Parser ──────────────────────────────────────────────────

    @staticmethod
    def _parse_response(content):
        """Parses the Agentic ATS JSON response."""
        try:
            # Clean up potential markdown code blocks
            clean_content = content.strip()
            if clean_content.startswith("```json"):
                clean_content = clean_content[7:]
            if clean_content.endswith("```"):
                clean_content = clean_content[:-3]

            data = json.loads(clean_content)

            # Extract score from recruiter_view
            recruiter_view = data.get("recruiter_view", {})
            score = recruiter_view.get("match_score", 0)

            # If everything is valid, return score and the full JSON string
            return int(score), json.dumps(data)
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            print(f"[AI] JSON Parse Error: {e}")
            # Fallback to simple parsing if JSON fails (rare with Gemini response_mime_type)
            return 0, content

import json
import logging
import re
import time

from AI.parsers import (
    parse_ai_response,
    extract_summary_and_analysis as _extract_summary_and_analysis,
    repair_truncated_json as _repair_truncated_json,
    get_summary_from_dict as _get_summary_from_dict,
)

import requests
from django.conf import settings
from google import genai
from google.genai import types

logger = logging.getLogger("ai.service")

# ─── Model Pipeline ───────────────────────────────────────────────────────────
# Primary: gemini-2.5-flash      — more reasoning capacity
# Fallback: gemini-2.5-flash-lite  — fastest, highest free-tier quota
MODEL_PIPELINE = [
    ("gemini-2.5-flash", 2),
    ("gemini-2.5-flash-lite", 2),
]

# Reusable client singleton (avoids re-init overhead per call)
_client_cache = {}


def _get_client(api_key):
    """Returns a cached Gemini client to avoid repeated initialization."""
    if api_key not in _client_cache:
        _client_cache[api_key] = genai.Client(api_key=api_key)
    return _client_cache[api_key]


class AIServiceError(Exception):
    """Raised when all AI models in the pipeline fail."""
    pass


# ─── Experience Level Definitions ────────────────────────────────────────────
EXP_DEFINITIONS = {
    "ENTRY": {
        "label": "Entry Level / Fresher / Intern",
        "years_min": 0,
        "years_max": 2,
        "expectations": (
            "Foundational knowledge, academic projects acceptable, "
            "internship experience valued, no management expectation."
        ),
    },
    "MID": {
        "label": "Mid-Level (Individual Contributor)",
        "years_min": 3,
        "years_max": 5,
        "expectations": (
            "Hands-on production experience, owns features end-to-end, "
            "mentors juniors, works independently, strong domain competency."
        ),
    },
    "SENIOR": {
        "label": "Senior / Tech Lead",
        "years_min": 6,
        "years_max": 10,
        "expectations": (
            "Architects systems, drives technical decisions, leads code reviews, "
            "cross-functional collaboration, proven delivery of complex projects at scale."
        ),
    },
    "LEAD": {
        "label": "Principal / Staff / Director",
        "years_min": 10,
        "years_max": 99,
        "expectations": (
            "Strategic technology leadership, org-wide influence, "
            "defines engineering culture, deep subject matter expertise, "
            "executive-level communication."
        ),
    },
}


class AIService:
    # ─── Google Drive Helpers ─────────────────────────────────────────────

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

        for key, value in response.cookies.items():
            if key.startswith("download_warning"):
                url = f"https://drive.google.com/uc?export=download&confirm={value}&id={file_id}"
                response = session.get(url, timeout=30)
                break

        content_type = response.headers.get("Content-Type", "")
        if response.status_code == 200 and "text/html" not in content_type.lower():
            print(f"[AI] Downloaded from Google Drive: {file_id} ({len(response.content)} bytes)")
            return response.content, None

        if "text/html" in content_type.lower():
            print(f"[AI] Google Drive file is restricted: {file_id}")
            return (
                None,
                "Resume file is restricted on Google Drive. Set sharing to 'Anyone with the link'.",
            )

        print(f"[AI] Google Drive download failed: {file_id} (HTTP {response.status_code})")
        return None, f"Google Drive download failed (HTTP {response.status_code})"

    # ─── PDF Download ─────────────────────────────────────────────────────

    @staticmethod
    def download_pdf(pdf_url):
        """Downloads a PDF from any URL. Returns (bytes, error_reason)."""
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
            resp = requests.get(pdf_url, headers=headers, timeout=30, allow_redirects=True)
            if resp.status_code == 200:
                return resp.content, None

            return None, f"Download failed (HTTP {resp.status_code})"

        except requests.exceptions.Timeout:
            return None, "Download timed out — file server too slow"
        except Exception as e:
            return None, f"Download error: {str(e)}"

    @staticmethod
    def extract_text_from_pdf(pdf_bytes):
        """Extracts text from PDF bytes using pypdf for clean text reference."""
        try:
            import io
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(pdf_bytes))
            text_parts = []
            for i, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(f"--- PAGE {i+1} ---\n{page_text}")
            return "\n\n".join(text_parts).strip()
        except Exception as e:
            logger.error(f"[AI] Text extraction failed: {e}")
            return ""

    @staticmethod
    def call_kimi_api(prompt):
        """Calls Kimi API using the official OpenAI client SDK with Azure AD or Moonshot key."""
        from openai import OpenAI
        from django.conf import settings

        api_key = getattr(settings, "KIMI_API_KEY", None)
        azure_endpoint = getattr(settings, "AZURE_KIMI_ENDPOINT", "")
        if not azure_endpoint:
            azure_endpoint = getattr(settings, "AZUREPROJECT_ENDPOINT", "")

        deployment_name = getattr(settings, "AZURE_KIMI_DEPLOYMENT", "")
        if not deployment_name:
            deployment_name = "Kimi-K2.6"

        if azure_endpoint:
            from urllib.parse import urlparse
            parsed = urlparse(azure_endpoint)
            if "/openai/v1" not in azure_endpoint and "/v1" not in azure_endpoint:
                base_url = f"{parsed.scheme}://{parsed.netloc}/openai/v1"
            else:
                base_url = azure_endpoint

            if not api_key:
                from azure.identity import DefaultAzureCredential, get_bearer_token_provider
                token_provider = get_bearer_token_provider(
                    DefaultAzureCredential(), "https://ai.azure.com/.default"
                )
                client = OpenAI(
                    base_url=base_url,
                    api_key=token_provider
                )
                print(f"[AI] Initialized Kimi client using Azure Entra ID bearer token provider. Endpoint: {base_url}")
            else:
                client = OpenAI(
                    base_url=base_url,
                    api_key=api_key
                )
                print(f"[AI] Initialized Kimi client using Azure static API key. Endpoint: {base_url}")
        else:
            if not api_key:
                raise ValueError("Kimi API key is not configured.")
            client = OpenAI(
                base_url="https://api.moonshot.cn/v1",
                api_key=api_key
            )
            print("[AI] Initialized Kimi client using Moonshot direct URL.")

        completion = client.chat.completions.create(
            model=deployment_name,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.0,
            timeout=180.0
        )

        if completion.choices and len(completion.choices) > 0:
            return completion.choices[0].message.content
        else:
            raise ValueError(f"Unexpected empty completion choices: {completion}")

    @staticmethod
    def call_grok_api(prompt):
        """Calls Grok API using the official OpenAI client SDK with Azure AD or static key."""
        from openai import OpenAI
        from django.conf import settings

        api_key = getattr(settings, "GROK_API_KEY", None)
        endpoint = getattr(settings, "AZURE_GROK_ENDPOINT", "")
        if not endpoint:
            endpoint = "https://lakkavaramlinus-1936-resource.services.ai.azure.com/openai/v1"

        deployment_name = getattr(settings, "AZURE_GROK_DEPLOYMENT", "")
        if not deployment_name:
            deployment_name = "grok-4-20-non-reasoning"

        if not api_key:
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider
            token_provider = get_bearer_token_provider(
                DefaultAzureCredential(), "https://ai.azure.com/.default"
            )
            client = OpenAI(
                base_url=endpoint,
                api_key=token_provider
            )
            print("[AI] Initialized Grok client using Azure Entra ID bearer token provider.")
        else:
            client = OpenAI(
                base_url=endpoint,
                api_key=api_key
            )
            print("[AI] Initialized Grok client using Azure static API key.")

        completion = client.chat.completions.create(
            model=deployment_name,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.0,
            timeout=180.0
        )

        if completion.choices and len(completion.choices) > 0:
            return completion.choices[0].message.content
        else:
            raise ValueError(f"Unexpected empty completion choices: {completion}")

    @staticmethod
    def call_grok_4_1_api(prompt):
        """Calls Grok 4.1 API using the official OpenAI client SDK with Azure AD or static key."""
        from openai import OpenAI
        from django.conf import settings

        api_key = getattr(settings, "AZURE_GROK_API_2", None)
        endpoint = getattr(settings, "AZURE_GROK_ENDPOINT_2", "")
        deployment_name = "grok-4-1-fast-non-reasoning"

        if not endpoint:
            raise ValueError("Grok 4.1 endpoint is not configured.")

        base_url = endpoint.split("/chat/completions")[0]
        from urllib.parse import urlparse
        parsed = urlparse(base_url)
        if "/openai/v1" not in base_url and "/v1" not in base_url:
            base_url = f"{parsed.scheme}://{parsed.netloc}/openai/v1"

        if not api_key:
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider
            token_provider = get_bearer_token_provider(
                DefaultAzureCredential(), "https://ai.azure.com/.default"
            )
            client = OpenAI(
                base_url=base_url,
                api_key=token_provider
            )
            print(f"[AI] Initialized Grok 4.1 client using Azure Entra ID token provider. Endpoint: {base_url}")
        else:
            client = OpenAI(
                base_url=base_url,
                api_key=api_key
            )
            print(f"[AI] Initialized Grok 4.1 client using Azure static API key. Endpoint: {base_url}")

        completion = client.chat.completions.create(
            model=deployment_name,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.0,
            timeout=180.0
        )

        if completion.choices and len(completion.choices) > 0:
            return completion.choices[0].message.content
        else:
            raise ValueError(f"Unexpected empty completion choices: {completion}")

    # ─── World-Class ATS Resume Analysis ──────────────────────────────────

    @staticmethod
    def analyze_resume(job_title, job_brief, resume_url, selected_model=None, report_id=None):
        """
        Two-pass enterprise ATS screening engine.

        Pass 1 — Hard knockout layer: eliminates unqualified candidates immediately.
        Pass 2 — Deep holistic scoring: weighted, tiered, multi-dimensional evaluation.

        job_brief dict keys:
          description, required_skills, experience_level, job_type,
          work_mode, department, salary_min, salary_max, currency
        """
        # Determine key to validate based on selected model
        if selected_model in ("kimi", "Kimi-K2.6"):
            api_key = getattr(settings, "KIMI_API_KEY", None)
            azure_endpoint = getattr(settings, "AZURE_KIMI_ENDPOINT", "") or getattr(settings, "AZUREPROJECT_ENDPOINT", "")
            if not api_key and not azure_endpoint:
                return None, "Kimi API key or Azure project endpoint must be configured."
        elif selected_model in ("grok", "grok-4-20-non-reasoning"):
            api_key = getattr(settings, "GROK_API_KEY", None)
            azure_endpoint = getattr(settings, "AZURE_GROK_ENDPOINT", "")
            if not api_key and not azure_endpoint:
                return None, "Grok API key or Azure Grok endpoint must be configured."
        elif selected_model in ("grok-4.1-non-reasoning", "grok-4-1-fast-non-reasoning"):
            api_key = getattr(settings, "AZURE_GROK_API_2", None)
            azure_endpoint = getattr(settings, "AZURE_GROK_ENDPOINT_2", "")
            if not api_key and not azure_endpoint:
                return None, "Grok 4.1 API key or Azure Grok 4.1 endpoint must be configured."
        else:
            api_key = getattr(settings, "GEMINI_API_KEY", None)
            if not api_key:
                return None, "Gemini API key is not configured."

        # Check cancellation before download
        if report_id:
            from django.db import connection
            from AI.models import AIScreeningReport
            try:
                connection.close()
                if not AIScreeningReport.objects.filter(id=report_id, is_deleted=False).exists():
                    return None, "Cancelled"
            except Exception as e:
                print(f"[AI] Failed check before download: {e}")

        # ── Step 1: Download Resume PDF ────────────────────────────────────
        pdf_bytes, download_error = AIService.download_pdf(resume_url)
        if not pdf_bytes:
            return None, download_error or "Could not download resume"

        # ── Step 1b: Extract Plain Text from PDF ────────────────────────────
        extracted_text = AIService.extract_text_from_pdf(pdf_bytes)

        # Check cancellation after download & text extraction completes
        if report_id:
            from django.db import connection
            from AI.models import AIScreeningReport
            try:
                connection.close()
                if not AIScreeningReport.objects.filter(id=report_id, is_deleted=False).exists():
                    print(f"[AI] Report {report_id} has been cancelled during download/extraction. Aborting.")
                    return None, "Cancelled"
            except Exception as e:
                print(f"[AI] Failed check after download: {e}")

        # ── Step 2: Unpack & Enrich Job Brief ─────────────────────────────
        required_skills  = job_brief.get("required_skills", "Not specified")
        experience_level = job_brief.get("experience_level", "ENTRY")
        job_type         = job_brief.get("job_type", "FULL_TIME")
        work_mode        = job_brief.get("work_mode", "ONSITE")
        department       = job_brief.get("department", "")
        salary_min       = job_brief.get("salary_min", "")
        salary_max       = job_brief.get("salary_max", "")
        currency         = job_brief.get("currency", "INR")
        description      = job_brief.get("description", "")[:3000]
        job_category     = job_brief.get("job_category", "IT")

        exp_def = EXP_DEFINITIONS.get(experience_level, EXP_DEFINITIONS["ENTRY"])
        exp_label        = exp_def["label"]
        exp_years_min    = exp_def["years_min"]
        exp_years_max    = exp_def["years_max"]
        exp_expectations = exp_def["expectations"]

        salary_range = ""
        if salary_min and salary_max:
            salary_range = f"{currency} {salary_min}–{salary_max} per annum"
        elif salary_min:
            salary_range = f"From {currency} {salary_min} per annum"

        try:
            # ── Step 3: Initialize Client / Route Kimi / Grok ──────────────
            if selected_model in ("kimi", "Kimi-K2.6", "grok", "grok-4-20-non-reasoning"):
                client = None
                pdf_part = None
            else:
                client = _get_client(api_key)
                pdf_part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")

            # ── Step 4: World-Class 20-Dimension ATS Prompt ──────────────
            prompt = f"""You are an enterprise-grade AI ATS engine operating at the standard of
Greenhouse, Lever, and Workday — used by the world's top 1% hiring organizations.

Your task is a COMPREHENSIVE 20-DIMENSION evaluation of the candidate's resume
(provided both as binary PDF and as extracted text below) against the job specification.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
POSITION SPECIFICATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Job Title         : {job_title}
Job Category      : {job_category}
Department        : {department or "Not specified"}
Employment Type   : {job_type.replace("_", " ").title()}
Work Mode         : {work_mode.replace("_", " ").title()}
Seniority Level   : {exp_label}
Experience Range  : {exp_years_min}–{exp_years_max} years
Compensation      : {salary_range or "Not disclosed"}

REQUIRED SKILLS (treat as must-have unless explicitly labelled nice-to-have):
{required_skills}

JOB DESCRIPTION:
{description}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXTRACTED RESUME TEXT (Use this for precise spelling, keyword matching, and reference):
{extracted_text or "No text could be extracted; rely on the PDF attachment."}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SENIORITY EXPECTATIONS FOR THIS ROLE:
{exp_expectations}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

══════════════════════════════════════════════════════
SKILLS MATCHING & SYNONYM RULES (CRITICAL)
══════════════════════════════════════════════════════
To prevent false-negative skill mismatch flags:
1. Map technology synonyms and standard aliases as matches:
   - "sql" → MySQL, PostgreSQL, SQLite, MS SQL, SQL Server, Oracle, PL/SQL, T-SQL, NoSQL
   - "pytorch" → PyTorch, pytorch, torch
   - "tensorflow" → TensorFlow, tensorflow, keras
   - "scikit learn" → scikit-learn, sklearn
   - "mongodb" → MongoDB, Mongo
   - "react" → ReactJS, React.js, React
   - "django" → Django, django-rest-framework, DRF
   - "node" → Node.js, NodeJS, Express
   - "aws" → Amazon Web Services, S3, EC2, Lambda, CloudFront
   - "gcp" → Google Cloud, BigQuery, Cloud Functions
   - "ci/cd" → Jenkins, GitHub Actions, CircleCI, GitLab CI
2. Search EVERY section of the resume (including bullet points, sidebar skills, projects, and university/course projects). Do NOT mark a skill as missing if it appears anywhere.
3. Be extremely precise: if a skill is explicitly listed (e.g., PyTorch), do NOT count it as missing.

══════════════════════════════════════════════════════
PASS 1 — HARD KNOCKOUT EVALUATION
══════════════════════════════════════════════════════
Evaluate these knockout criteria FIRST. If any apply, cap the final match_score
and set knockout_applied=true with a clear knockout_reason.

KNOCKOUT RULE 1 — Critical Skills Deficit:
  If matched_skills / total_required_skills < 0.40:
    → max_score = 28, knockout_reason = "Fails critical skills threshold (< 40% match)"

KNOCKOUT RULE 2 — Severe Experience Deficit:
  If candidate's total relevant years < 50% of exp_years_min ({exp_years_min} yrs):
    → max_score = 35, knockout_reason = "Severe experience deficit (< 50% of minimum)"

KNOCKOUT RULE 3 — Domain Mismatch:
  If the candidate has ZERO experience in the role's domain/industry and the role is MID/SENIOR/LEAD:
    → max_score = 30, knockout_reason = "No domain relevance for {exp_label} role"

KNOCKOUT RULE 4 — Resume Integrity Failure:
  If resume contains: (a) contradictory employment dates, (b) AI-generated boilerplate text
  with no specifics, (c) phantom companies, (d) inflated titles unsupported by responsibilities:
    → max_score = 20, knockout_reason = "Resume integrity failure — potential fabrication"

══════════════════════════════════════════════════════
PASS 2 — 20-DIMENSION DEEP ANALYSIS
══════════════════════════════════════════════════════

CATEGORY 1 — PERSONAL INFORMATION EXTRACTION
  Extract: full_name, email, phone, location, linkedin, github, portfolio, website.
  Validate: Is email valid? Is phone present? Are professional links present?

CATEGORY 2 — RESUME COMPLETENESS (0–100)
  Score each section's presence and quality:
  - Profile Summary (0–15)
  - Experience (0–25)
  - Education (0–15)
  - Skills (0–15)
  - Projects (0–10)
  - Certifications (0–5)
  - Links/Portfolio (0–5)
  - Achievements (0–10)
  Total completeness = sum of all sections.

CATEGORY 3 — PROFESSIONAL SUMMARY ANALYSIS
  Evaluate: Is a summary present? Does it mention years of experience?
  Does it state domain/specialization? Does it list key skills?
  Rate: STRONG / AVERAGE / WEAK / MISSING

CATEGORY 4 — SKILLS ANALYSIS (30% weight)
  Technical Skills: Categorize into Programming, Frameworks, Databases, Cloud, DevOps, AI/ML, Tools.
  Soft Skills: Leadership, Communication, Problem Solving, Teamwork, etc.
  For each required skill, assess at three tiers:
    Tier A (Demonstrated): Used in production/shipped projects → full pts
    Tier B (Mentioned):    Listed but no evidence of real usage → half pts
    Tier C (Absent):       Not found anywhere → 0 pts
  Score = sum(tier_scores) / total_required_skills × 30

CATEGORY 5 — EXPERIENCE ANALYSIS (25% weight)
  Extract each role: company, title, start_date, end_date, duration_years.
  Calculate: total_experience, relevant_experience, management_experience (in years).
  Evaluate quality vs quantity of experience against the seniority expectations.
  Score 0–25 based on match quality.

CATEGORY 6 — JOB STABILITY ANALYSIS
  Detect: job hopping patterns, employment gaps, frequent switches, long tenures.
  Calculate: average tenure across all roles.
  Output: stability_score (0–100), risk_level (Low/Medium/High), observation text.

CATEGORY 7 — EDUCATION ANALYSIS (10% weight)
  Extract: degree, university, specialization, graduation_year, cgpa/gpa (if available).
  Evaluate relevance to the role.
  Score 0–10.

CATEGORY 8 — CERTIFICATION ANALYSIS (5% weight)
  Extract all certifications with issuing authority.
  Calculate relevance_score for each cert against the job requirements.
  Score 0–5.

CATEGORY 9 — PROJECT ANALYSIS (10% weight)
  Extract: project name, role, tech stack, duration, impact.
  Evaluate: complexity (High/Medium/Low), scale, relevance to the role.
  Score 0–10.

CATEGORY 10 — ATS KEYWORD MATCH (10% weight)
  Compare the required skills from the JD against the resume.
  List each required keyword as found (true/false).
  Calculate: keyword_match_percentage.
  Score 0–10.

CATEGORY 11 — MISSING KEYWORDS ANALYSIS
  List all required keywords NOT found in the resume.
  Assess impact of each missing keyword: critical / moderate / low.

CATEGORY 12 — ROLE FIT ANALYSIS
  Determine candidate's assessed level: Junior / Mid-Level / Senior / Lead / Manager / Architect.
  Compare against the role's required seniority ({exp_label}).
  Verdict: PERFECT_FIT / GOOD_FIT / PARTIAL_FIT / OVERQUALIFIED / UNDERQUALIFIED.

CATEGORY 13 — INDUSTRY EXPERIENCE
  Extract all industries/domains the candidate has worked in:
  e.g., Fintech, Healthcare, E-Commerce, SaaS, EdTech, HRTech, AI, etc.
  Flag which are relevant to THIS role.

CATEGORY 14 — CAREER PROGRESSION ANALYSIS
  Map the progression path (e.g., Developer → Senior Developer → Lead → Manager).
  Assess: Is career growth consistent? Are there demotions? Is progression valid?
  career_growth_score (0–100).

CATEGORY 15 — ACHIEVEMENT ANALYSIS (5% weight)
  Detect quantified achievements:
  - Revenue generated / cost saved / performance improved
  - Team size managed / users served / uptime maintained
  List each achievement with its metric.
  Score 0–5.

CATEGORY 16 — RESUME QUALITY ANALYSIS (5% weight)
  Evaluate: grammar, formatting, structure, readability, spelling, professionalism.
  resume_quality_score (0–100).
  Score 0–5 for the weighted total.

CATEGORY 17 — CANDIDATE STRENGTHS
  Generate a list of the top 3–5 key strengths with reasoning.

CATEGORY 18 — CANDIDATE RISKS / CONCERNS
  Generate a list of potential risks/concerns.

CATEGORY 19 — AI RECRUITER RECOMMENDATION
  Based on the full 20-dimension analysis, output one of:
  STRONG_HIRE / HIRE / CONSIDER / WEAK_CONSIDER / REJECT
  Include a detailed reasoning paragraph.

CATEGORY 20 — OVERALL ATS SCORE (Weighted)
  Calculate the final match_score using these weights:
    Skills Match (Cat 4)      : 30%
    Experience (Cat 5)        : 25%
    Education (Cat 7)         : 10%
    Projects (Cat 9)          : 10%
    Keywords (Cat 10)         : 10%
    Achievements (Cat 15)     : 5%
    Resume Quality (Cat 16)   : 5%
    Certifications (Cat 8)    : 5%
  match_score = weighted sum, clamped 0–100.

══════════════════════════════════════════════════════
SCORING CALIBRATION REFERENCE
══════════════════════════════════════════════════════
  90–100: Exceptional (< 2% of applicants) — immediate shortlist
  75–89:  Strong match — schedule technical screen
  60–74:  Qualified — worth interviewing to verify gaps
  45–59:  Partial match — hold unless pipeline is thin
  30–44:  Weak match — reject unless role is hard-to-fill
  0–29:   Knockout / Disqualified

BIAS MITIGATION DIRECTIVE:
  Do NOT allow these factors to influence scoring:
  - Candidate name, gender markers, university prestige
  - Employment gaps (evaluate explanation if given, not the gap itself)
  - Non-linear career paths (evaluate demonstrated competency only)
  Flag in bias_flags if any of these might have influenced your evaluation.

══════════════════════════════════════════════════════
OUTPUT SPECIFICATION
══════════════════════════════════════════════════════
Return ONLY valid JSON with NO markdown fences, NO prose before/after:

{{
  "intelligence": {{
    "candidate_info": {{
      "full_name": "",
      "email": "",
      "phone": "",
      "location": "",
      "linkedin_url": "",
      "github_url": "",
      "portfolio_url": "",
      "website_url": "",
      "contact_validation": {{
        "email_valid": true,
        "phone_present": true,
        "has_professional_links": true
      }}
    }},
    "resume_completeness": {{
      "profile_summary": 0,
      "experience": 0,
      "education": 0,
      "skills": 0,
      "projects": 0,
      "certifications": 0,
      "links": 0,
      "achievements": 0,
      "total_score": 0
    }},
    "professional_summary": {{
      "present": true,
      "mentions_experience_years": true,
      "mentions_domain": true,
      "mentions_key_skills": true,
      "quality": "STRONG|AVERAGE|WEAK|MISSING",
      "summary_text": ""
    }},
    "career_summary": {{
      "primary_role": "",
      "current_or_last_title": "",
      "current_or_last_company": "",
      "specialization": "",
      "total_years_experience": 0,
      "relevant_years_experience": 0,
      "management_years_experience": 0,
      "career_level_assessed": "Junior|Mid-Level|Senior|Lead|Manager|Architect",
      "career_progression_valid": true,
      "progression_note": ""
    }},
    "skills_assessment": {{
      "technical_skills": {{
        "programming": [],
        "frameworks": [],
        "databases": [],
        "cloud": [],
        "devops": [],
        "ai_ml": [],
        "tools": []
      }},
      "soft_skills": [],
      "matched_required": [
        {{"skill": "", "tier": "A|B", "evidence": ""}}
      ],
      "missing_required": [
        {{"skill": "", "impact": "critical|moderate|low"}}
      ],
      "additional_valuable": [],
      "skills_match_percentage": 0,
      "skills_score": 0
    }},
    "experience_timeline": [
      {{
        "company": "",
        "role": "",
        "start_date": "",
        "end_date": "",
        "duration_years": 0,
        "seniority_level": "junior|mid|senior|lead|manager",
        "is_management": false,
        "technologies": [],
        "key_achievements": [],
        "domain_relevant": true
      }}
    ],
    "job_stability": {{
      "stability_score": 0,
      "average_tenure_years": 0,
      "risk_level": "Low|Medium|High",
      "job_hopping_detected": false,
      "employment_gaps": [],
      "longest_tenure_years": 0,
      "observation": ""
    }},
    "education": [
      {{
        "institution": "",
        "degree": "",
        "field": "",
        "year": "",
        "cgpa": "",
        "relevant": true
      }}
    ],
    "certifications": [
      {{
        "name": "",
        "issuing_authority": "",
        "year": "",
        "relevance_score": 0
      }}
    ],
    "projects": [
      {{
        "name": "",
        "role": "",
        "description": "",
        "tech_stack": [],
        "duration": "",
        "impact_description": "",
        "impact_quantified": false,
        "complexity": "High|Medium|Low",
        "scale": "",
        "relevance_score": 0
      }}
    ],
    "keyword_match": {{
      "required_keywords": [
        {{"keyword": "", "found": true}}
      ],
      "keyword_match_percentage": 0,
      "keywords_score": 0
    }},
    "missing_keywords": [
      {{"keyword": "", "impact": "critical|moderate|low"}}
    ],
    "role_fit": {{
      "assessed_level": "Junior|Mid-Level|Senior|Lead|Manager|Architect",
      "required_level": "{exp_label}",
      "fit_verdict": "PERFECT_FIT|GOOD_FIT|PARTIAL_FIT|OVERQUALIFIED|UNDERQUALIFIED",
      "fit_detail": ""
    }},
    "industry_experience": {{
      "sectors": [],
      "relevant_sectors": [],
      "has_domain_experience": true
    }},
    "career_progression": {{
      "progression_path": [],
      "career_growth_score": 0,
      "consistent_growth": true,
      "has_demotions": false,
      "progression_note": ""
    }},
    "achievements": [
      {{
        "description": "",
        "metric": "",
        "category": "revenue|cost_savings|performance|team|users|other"
      }}
    ],
    "resume_quality": {{
      "grammar_score": 0,
      "formatting_score": 0,
      "structure_score": 0,
      "readability_score": 0,
      "professionalism_score": 0,
      "resume_quality_score": 0,
      "issues": []
    }},
    "experience_gap_analysis": {{
      "required_years_min": {exp_years_min},
      "required_years_max": {exp_years_max},
      "candidate_total_years": 0,
      "candidate_relevant_years": 0,
      "gap_years": 0,
      "verdict": "MEETS|BELOW|OVERQUALIFIED",
      "detail": ""
    }},
    "integrity_signals": {{
      "resume_ai_probability": 0,
      "date_consistency_score": 0,
      "specificity_score": 0,
      "red_flags": [],
      "positive_signals": []
    }}
  }},
  "recruiter_view": {{
    "match_score": 0,
    "score_breakdown": {{
      "skills_match": 0,
      "experience": 0,
      "education": 0,
      "projects": 0,
      "keywords": 0,
      "achievements": 0,
      "resume_quality": 0,
      "certifications": 0,
      "total_before_knockout": 0
    }},
    "score_weights": {{
      "skills_match": 30,
      "experience": 25,
      "education": 10,
      "projects": 10,
      "keywords": 10,
      "achievements": 5,
      "resume_quality": 5,
      "certifications": 5
    }},
    "knockout_applied": false,
    "knockout_rule_triggered": "",
    "knockout_reason": "",
    "recommendation": "STRONG_HIRE|HIRE|CONSIDER|WEAK_CONSIDER|REJECT",
    "recommendation_reason": "",
    "strengths": [],
    "concerns": [],
    "red_flags": [],
    "skills_verdict": "",
    "experience_verdict": "",
    "career_progression_verdict": "",
    "bias_flags": [],
    "trust_score": 0,
    "recruiter_action_memo": "",
    "recommended_action": "",
    "explanation": "",
    "tailored_interview_questions": [
      {{
        "question": "",
        "dimension": "skills|experience|culture|leadership|problem_solving",
        "targets_gap": true,
        "expected_answer_hint": ""
      }}
    ]
  }}
}}"""

            # Global Enterprise Speed Instruction (applied to all models)
            speed_instruction = (
                "\n\nENTERPRISE SPEED INSTRUCTION (CRITICAL - MUST FOLLOW TO PREVENT TIMEOUTS):\n"
                "To achieve under 2 minutes for processing 100+ resumes, follow these constraints strictly:\n"
                "1. For all general description, explanation, reasoning, rationale, action_memo, and summary_text fields: write at least 2 descriptive sentences (minimum 2 lines of details, around 20-30 words).\n"
                "2. For skills_assessment (matched_required and missing_required arrays): you MUST list ALL matching and non-matching skills. Do NOT cap these arrays. List every single skill precisely with full details and exact evidence from the resume.\n"
                "3. For other arrays (projects, education, certifications, achievements, tailored_interview_questions): include a maximum of 1 item to optimize speed.\n"
                "4. For experience_timeline: include a maximum of 1-2 items (the most recent or relevant roles).\n"
                "5. Absolutely do NOT generate 'pipeline_disposition' or 'hiring_confidence'. Remove them from the output structure.\n"
                "6. Return only valid JSON. Do not output any markdown blocks (like ```json), introduction, or conclusion."
            )
            prompt += speed_instruction

            # ── Step 5: Invoke AI Model / Pipeline ───────────────────
            if selected_model in ("grok", "grok-4-20-non-reasoning"):
                print(f"[AI] Calling Grok API (model: {selected_model})...")
                last_error = None
                for attempt in range(1, 4):
                    if report_id:
                        from django.db import connection
                        from AI.models import AIScreeningReport
                        try:
                            connection.close()
                            if not AIScreeningReport.objects.filter(id=report_id, is_deleted=False).exists():
                                return None, "Cancelled"
                        except Exception as e:
                            print(f"[AI] Failed check in Grok attempt: {e}")
                    try:
                        t0 = time.time()
                        grok_response = AIService.call_grok_api(prompt)
                        elapsed = time.time() - t0
                        print(f"[AI] Grok responded in {elapsed:.1f}s")
                        
                        if report_id:
                            from django.db import connection
                            from AI.models import AIScreeningReport
                            try:
                                connection.close()
                                if not AIScreeningReport.objects.filter(id=report_id, is_deleted=False).exists():
                                    print(f"[AI] Report {report_id} has been cancelled. Aborting Grok parser.")
                                    return None, "Cancelled"
                            except Exception as e:
                                pass

                        if grok_response:
                            score, analysis = AIService._parse_response(grok_response)
                            if score is not None:
                                return score, analysis
                            else:
                                last_error = "Grok response parser returned None score"
                        else:
                            last_error = "Empty response from Grok"
                    except Exception as e:
                        last_error = str(e)
                        print(f"[AI] Grok attempt {attempt} failed: {last_error}")
                        if "429" in last_error or "rate" in last_error.lower() or "limit" in last_error.lower():
                            sleep_time = attempt * 3
                            print(f"[AI] Grok rate limit hit, sleeping {sleep_time}s")
                            time.sleep(sleep_time)
                        else:
                            time.sleep(1)
                return 0, f"Grok analysis failed: {last_error}"

            if selected_model in ("grok-4.1-non-reasoning", "grok-4-1-fast-non-reasoning"):
                print(f"[AI] Calling Grok 4.1 API (model: {selected_model})...")
                last_error = None
                for attempt in range(1, 4):
                    if report_id:
                        from django.db import connection
                        from AI.models import AIScreeningReport
                        try:
                            connection.close()
                            if not AIScreeningReport.objects.filter(id=report_id, is_deleted=False).exists():
                                return None, "Cancelled"
                        except Exception as e:
                            print(f"[AI] Failed check in Grok 4.1 attempt: {e}")
                    try:
                        t0 = time.time()
                        grok_response = AIService.call_grok_4_1_api(prompt)
                        elapsed = time.time() - t0
                        print(f"[AI] Grok 4.1 responded in {elapsed:.1f}s")
                        
                        if report_id:
                            from django.db import connection
                            from AI.models import AIScreeningReport
                            try:
                                connection.close()
                                if not AIScreeningReport.objects.filter(id=report_id, is_deleted=False).exists():
                                    print(f"[AI] Report {report_id} has been cancelled. Aborting Grok 4.1 parser.")
                                    return None, "Cancelled"
                            except Exception as e:
                                pass

                        if grok_response:
                            score, analysis = AIService._parse_response(grok_response)
                            if score is not None:
                                return score, analysis
                            else:
                                last_error = "Grok 4.1 response parser returned None score"
                        else:
                            last_error = "Empty response from Grok 4.1"
                    except Exception as e:
                        last_error = str(e)
                        print(f"[AI] Grok 4.1 attempt {attempt} failed: {last_error}")
                        if "429" in last_error or "rate" in last_error.lower() or "limit" in last_error.lower():
                            sleep_time = attempt * 3
                            print(f"[AI] Grok 4.1 rate limit hit, sleeping {sleep_time}s")
                            time.sleep(sleep_time)
                        else:
                            time.sleep(1)
                return 0, f"Grok 4.1 analysis failed: {last_error}"

            if selected_model in ("kimi", "Kimi-K2.6"):
                print(f"[AI] Calling Kimi API (model: {selected_model})...")
                last_error = None
                for attempt in range(1, 4):
                    if report_id:
                        from django.db import connection
                        from AI.models import AIScreeningReport
                        try:
                            connection.close()
                            if not AIScreeningReport.objects.filter(id=report_id, is_deleted=False).exists():
                                return None, "Cancelled"
                        except Exception as e:
                            print(f"[AI] Failed check in Kimi attempt: {e}")
                    try:
                        t0 = time.time()
                        kimi_response = AIService.call_kimi_api(prompt)
                        elapsed = time.time() - t0
                        print(f"[AI] Kimi responded in {elapsed:.1f}s")
                        
                        if report_id:
                            from django.db import connection
                            from AI.models import AIScreeningReport
                            try:
                                connection.close()
                                if not AIScreeningReport.objects.filter(id=report_id, is_deleted=False).exists():
                                    print(f"[AI] Report {report_id} has been cancelled. Aborting Kimi parser.")
                                    return None, "Cancelled"
                            except Exception as e:
                                pass

                        if kimi_response:
                            score, analysis = AIService._parse_response(kimi_response)
                            if score is not None:
                                return score, analysis
                            else:
                                last_error = "Kimi response parser returned None score"
                        else:
                            last_error = "Empty response from Kimi"
                    except Exception as e:
                        last_error = str(e)
                        print(f"[AI] Kimi attempt {attempt} failed: {last_error}")
                        if "429" in last_error or "rate" in last_error.lower() or "limit" in last_error.lower():
                            sleep_time = attempt * 3
                            print(f"[AI] Kimi rate limit hit, sleeping {sleep_time}s")
                            time.sleep(sleep_time)
                        else:
                            time.sleep(1)
                return 0, f"Kimi analysis failed: {last_error}"

            # Whitelisted Gemini 2+ and 3+ models
            ALLOWED_GEMINI_2_MODELS = [
                "gemini-3.5-flash",
                "gemini-3.5-flash-live",
                "gemini-3.0-flash-live",
                "gemini-3.1-pro-preview",
                "gemini-3.1-flash-lite",
                "gemini-3-pro-preview",
                "gemini-3-flash-preview",
                "gemini-2.5-flash",
                "gemini-2.5-flash-lite",
                "gemini-2.5-pro",
                "gemini-2.0-flash",
                "gemini-2.0-flash-thinking-exp",
                "gemini-2.0-pro-exp",
                "text-multilingual-embedding-002"
            ]

            pipeline = []
            if selected_model and selected_model in ALLOWED_GEMINI_2_MODELS:
                pipeline.append((selected_model, 2))
                # Add default fallbacks if different
                for m, retries in MODEL_PIPELINE:
                    if m != selected_model:
                        pipeline.append((m, retries))
            else:
                pipeline = MODEL_PIPELINE

            last_error = None
            for model_name, max_retries in pipeline:
                for attempt in range(1, max_retries + 1):
                    if report_id:
                        from django.db import connection
                        from AI.models import AIScreeningReport
                        try:
                            connection.close()
                            if not AIScreeningReport.objects.filter(id=report_id, is_deleted=False).exists():
                                return None, "Cancelled"
                        except Exception as e:
                            print(f"[AI] Failed check in Gemini attempt: {e}")
                    try:
                        t0 = time.time()
                        print(f"[AI] Calling {model_name} (attempt {attempt})...")

                        response = client.models.generate_content(
                            model=model_name,
                            contents=[pdf_part, prompt],
                            config=types.GenerateContentConfig(
                                max_output_tokens=65536,
                                temperature=0.0,  # Fully deterministic — enterprise ATS must be consistent
                                response_mime_type="application/json",
                            ),
                        )

                        if response and response.text:
                            elapsed = time.time() - t0
                            print(f"[AI] {model_name} responded in {elapsed:.1f}s")

                            if report_id:
                                from django.db import connection
                                from AI.models import AIScreeningReport
                                try:
                                    connection.close()
                                    if not AIScreeningReport.objects.filter(id=report_id, is_deleted=False).exists():
                                        print(f"[AI] Report {report_id} has been cancelled. Aborting Gemini parser.")
                                        return None, "Cancelled"
                                except Exception as e:
                                    pass

                            score, analysis = AIService._parse_response(response.text)
                            if score is not None:
                                return score, analysis
                            else:
                                last_error = "Parser returned None score"
                        else:
                            last_error = "Empty response from Gemini"

                    except Exception as e:
                        last_error = str(e)
                        print(f"[AI] {model_name} attempt {attempt} failed: {last_error}")
                        if "429" in last_error or "quota" in last_error.lower():
                            sleep_time = min(2 ** attempt, 30)
                            print(f"[AI] Rate limit — sleeping {sleep_time}s")
                            time.sleep(sleep_time)
                        else:
                            time.sleep(1)

            return 0, f"AI analysis failed after all retries. Last error: {last_error}"

        except Exception as e:
            print(f"[AI] Outer analysis error: {e}")
            return 0, f"AI analysis failed: {str(e)}"

    # ─── Response Parser (delegates to AI.parsers) ────────────────────────

    @staticmethod
    def _parse_response(content):
        """Parse the ATS JSON response. Delegates to AI.parsers.parse_ai_response."""
        return parse_ai_response(content)

    @staticmethod
    def repair_truncated_json(json_str):
        """Repair truncated JSON. Delegates to AI.parsers.repair_truncated_json."""
        return _repair_truncated_json(json_str)

    @staticmethod
    def _get_summary_from_dict(d):
        """Extract summary from dict. Delegates to AI.parsers.get_summary_from_dict."""
        return _get_summary_from_dict(d)

    @staticmethod
    def extract_summary_and_analysis(ai_analysis_str):
        """Extract summary + analysis. Delegates to AI.parsers.extract_summary_and_analysis."""
        return _extract_summary_and_analysis(ai_analysis_str)

    @staticmethod
    def get_skills_match_pct(ai_analysis_str):
        """Extract skills match percentage from raw analysis JSON string."""
        if not ai_analysis_str:
            return 0
        try:
            import json
            analysis_str = ai_analysis_str.strip()
            if analysis_str.startswith('{'):
                analysis_obj = json.loads(analysis_str)
                return analysis_obj.get("intelligence", {}).get("skills_assessment", {}).get("skills_match_percentage", 0)
        except:
            pass
        return 0

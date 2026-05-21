import json
import logging
import re
import time

import requests
from django.conf import settings
from google import genai
from google.genai import types

logger = logging.getLogger("ai.service")

# ─── Model Pipeline ───────────────────────────────────────────────────────────
# Primary: gemini-2.5-flash-lite  — fastest, highest free-tier quota
# Fallback: gemini-2.5-flash      — more reasoning capacity
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

    # ─── World-Class ATS Resume Analysis ──────────────────────────────────

    @staticmethod
    def analyze_resume(job_title, job_brief, resume_url):
        """
        Two-pass enterprise ATS screening engine.

        Pass 1 — Hard knockout layer: eliminates unqualified candidates immediately.
        Pass 2 — Deep holistic scoring: weighted, tiered, multi-dimensional evaluation.

        job_brief dict keys:
          description, required_skills, experience_level, job_type,
          work_mode, department, salary_min, salary_max, currency
        """
        api_key = getattr(settings, "GEMINI_API_KEY", None)
        if not api_key:
            return None, "AI service not configured"

        # ── Step 1: Download Resume PDF ────────────────────────────────────
        pdf_bytes, download_error = AIService.download_pdf(resume_url)
        if not pdf_bytes:
            return None, download_error or "Could not download resume"

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
            # ── Step 3: Initialize Gemini Client ───────────────────────────
            client = _get_client(api_key)

            pdf_part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")

            # ── Step 4: World-Class ATS Prompt ─────────────────────────────
            prompt = f"""You are an enterprise-grade AI ATS engine operating at the standard of
Greenhouse, Lever, and Workday — used by the world's top 1% hiring organizations.

Your task is a TWO-PASS evaluation of the attached resume against the job specification below.

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
SENIORITY EXPECTATIONS FOR THIS ROLE:
{exp_expectations}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

══════════════════════════════════════════════════════
PASS 1 — HARD KNOCKOUT EVALUATION
══════════════════════════════════════════════════════
Evaluate these knockout criteria FIRST. If any apply, cap the final match_score
and set knockout_applied=true with a clear knockout_reason.

KNOCKOUT RULE 1 — Critical Skills Deficit:
  Count how many required skills the candidate has genuine, demonstrated experience with.
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
PASS 2 — DEEP HOLISTIC SCORING (100 points total)
══════════════════════════════════════════════════════
Score each dimension independently. Apply knockout cap to the final match_score if triggered.

DIMENSION 1 — SKILLS DEPTH & BREADTH (35 points)
  For each required skill, assess at three tiers:
    Tier A (Demonstrated): Used in production/shipped projects with specifics → full pts
    Tier B (Mentioned):    Listed but no evidence of real usage → half pts
    Tier C (Absent):       Not found anywhere in resume → 0 pts
  Score = sum(tier_scores) / total_required_skills × 35
  Note: Bonus up to +3 pts for rare/highly valuable additional skills relevant to role.

DIMENSION 2 — EXPERIENCE LEVEL CALIBRATION (25 points)
  Evaluate BOTH quantity (years) AND quality (seniority of roles held):
  ┌─────────────────────────────────────────────────────────────────┐
  │ Perfect match (years + role seniority align)         → 23–25   │
  │ Good match (within ±1 yr, seniority close)           → 18–22   │
  │ Partial (under by 1–2 yrs OR seniority mismatch)    → 10–17   │
  │ Significant gap (under by 3+ yrs OR major mismatch) → 3–9     │
  │ Overqualified for ENTRY/MID (overqualification risk) → 10–18   │
  │ No relevant experience                               → 0–4     │
  └─────────────────────────────────────────────────────────────────┘
  CRITICAL: Validate career progression. 8 years total but only junior-level
  role titles = inflated experience claim → penalize to 10–14 pts.

DIMENSION 3 — ROLE & DOMAIN RELEVANCE (20 points)
  Assess how directly their past work maps to THIS specific role:
  - Same role title, same tech stack, same domain → 17–20 pts
  - Adjacent role (e.g., backend for fullstack job), same domain → 12–16 pts
  - Different role, overlapping domain → 7–11 pts
  - Unrelated background entirely → 0–6 pts

DIMENSION 4 — IMPACT & ACHIEVEMENT QUALITY (12 points)
  World-class candidates quantify everything. Evaluate:
  - Hard metrics: user counts, performance improvements %, revenue impact → 10–12 pts
  - Soft metrics: "improved", "optimized" without numbers → 5–9 pts
  - Responsibilities listed, no achievements → 2–4 pts
  - Vague or copied job descriptions → 0–1 pt

DIMENSION 5 — LEARNING AGILITY & GROWTH SIGNALS (8 points)
  Evidence of continuous self-improvement beyond mandatory job duties:
  - Active side projects, OSS contributions, certifications, publications → 7–8 pts
  - Certifications or 1–2 side projects → 4–6 pts
  - No growth signals beyond job → 0–3 pts

══════════════════════════════════════════════════════
SCORING CALIBRATION REFERENCE
══════════════════════════════════════════════════════
These are the expected distributions for a competitive applicant pool:
  90–100: Exceptional (< 2% of applicants) — immediate shortlist
  75–89:  Strong match — schedule technical screen
  60–74:  Qualified — worth interviewing to verify gaps
  45–59:  Partial match — hold unless pipeline is thin
  30–44:  Weak match — reject unless role is hard-to-fill
  0–29:   Knockout / Disqualified

BIAS MITIGATION DIRECTIVE:
  Do NOT allow these factors to influence scoring:
  - Candidate name, gender markers, university prestige (evaluate skills, not pedigree)
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
      "portfolio_url": ""
    }},
    "career_summary": {{
      "primary_role": "",
      "current_or_last_title": "",
      "current_or_last_company": "",
      "specialization": "",
      "total_years_experience": 0,
      "relevant_years_experience": 0,
      "career_level_assessed": "",
      "career_progression_valid": true,
      "progression_note": ""
    }},
    "skills_assessment": {{
      "matched_required": [
        {{"skill": "", "tier": "A|B", "evidence": ""}}
      ],
      "missing_required": [
        {{"skill": "", "impact": "critical|moderate|low"}}
      ],
      "additional_valuable": [],
      "skills_match_percentage": 0
    }},
    "experience_timeline": [
      {{
        "company": "",
        "role": "",
        "start_date": "",
        "end_date": "",
        "duration_years": 0,
        "seniority_level": "junior|mid|senior|lead",
        "technologies": [],
        "key_achievements": [],
        "domain_relevant": true
      }}
    ],
    "projects": [
      {{
        "name": "",
        "description": "",
        "tech_stack": [],
        "scale": "",
        "impact_quantified": false,
        "impact_description": "",
        "relevance_score": 0
      }}
    ],
    "education": [
      {{
        "institution": "",
        "degree": "",
        "field": "",
        "year": "",
        "relevant": true
      }}
    ],
    "certifications": [],
    "experience_gap_analysis": {{
      "required_years_min": {exp_years_min},
      "required_years_max": {exp_years_max},
      "candidate_total_years": 0,
      "candidate_relevant_years": 0,
      "gap_years": 0,
      "verdict": "MEETS|BELOW|OVERQUALIFIED",
      "detail": ""
    }},
    "skills_gap_analysis": {{
      "total_required": 0,
      "matched_count": 0,
      "missing_count": 0,
      "missing_critical": [],
      "match_percentage": 0,
      "knockout_triggered": false
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
      "skills_depth": 0,
      "experience_calibration": 0,
      "role_domain_relevance": 0,
      "impact_quality": 0,
      "growth_signals": 0,
      "total_before_knockout": 0
    }},
    "knockout_applied": false,
    "knockout_rule_triggered": "",
    "knockout_reason": "",
    "pipeline_disposition": "SHORTLIST|INTERVIEW|HOLD|REJECT",
    "disposition_rationale": "",
    "strengths": [],
    "concerns": [],
    "red_flags": [],
    "skills_verdict": "",
    "experience_verdict": "",
    "career_progression_verdict": "",
    "hiring_confidence": "HIGH|MEDIUM|LOW",
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

            # ── Step 5: Invoke Gemini with Model Pipeline ───────────────────
            last_error = None
            for model_name, max_retries in MODEL_PIPELINE:
                for attempt in range(1, max_retries + 1):
                    try:
                        t0 = time.time()
                        print(f"[AI] Calling {model_name} (attempt {attempt})...")

                        response = client.models.generate_content(
                            model=model_name,
                            contents=[pdf_part, prompt],
                            config=types.GenerateContentConfig(
                                max_output_tokens=4096,
                                temperature=0.0,  # Fully deterministic — enterprise ATS must be consistent
                                response_mime_type="application/json",
                            ),
                        )

                        if response and response.text:
                            elapsed = time.time() - t0
                            print(f"[AI] {model_name} responded in {elapsed:.1f}s")
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

    # ─── Response Parser ──────────────────────────────────────────────────

    @staticmethod
    def _parse_response(content):
        """
        Parses the ATS JSON response.
        Extracts match_score and returns (score, full_json_string).
        Also applies post-parse score clamping and knockout cap enforcement.
        """
        try:
            clean = content.strip()
            # Strip any accidental markdown fences
            if clean.startswith("```json"):
                clean = clean[7:]
            if clean.startswith("```"):
                clean = clean[3:]
            if clean.endswith("```"):
                clean = clean[:-3]
            clean = clean.strip()

            data = json.loads(clean)
            rv = data.get("recruiter_view", {})

            raw_score = rv.get("match_score", 0)
            score = max(0, min(100, int(raw_score)))

            # Enforce knockout cap if flagged but score exceeds cap
            if rv.get("knockout_applied"):
                knockout_rule = rv.get("knockout_rule_triggered", "")
                if "RULE 1" in knockout_rule or "skills" in knockout_rule.lower():
                    score = min(score, 28)
                elif "RULE 2" in knockout_rule or "experience" in knockout_rule.lower():
                    score = min(score, 35)
                elif "RULE 3" in knockout_rule or "domain" in knockout_rule.lower():
                    score = min(score, 30)
                elif "RULE 4" in knockout_rule or "integrity" in knockout_rule.lower():
                    score = min(score, 20)

            # Write the clamped score back into the data
            data["recruiter_view"]["match_score"] = score

            # Ensure pipeline_disposition aligns with score if not set correctly
            disposition = rv.get("pipeline_disposition", "")
            if not disposition:
                if score >= 90:
                    disposition = "SHORTLIST"
                elif score >= 75:
                    disposition = "INTERVIEW"
                elif score >= 45:
                    disposition = "HOLD"
                else:
                    disposition = "REJECT"
                data["recruiter_view"]["pipeline_disposition"] = disposition

            logger.info(f"[AI Parser] Score={score} | Disposition={disposition} | Knockout={rv.get('knockout_applied', False)}")
            return score, json.dumps(data)

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            print(f"[AI] JSON Parse Error: {e}")
            return 0, content

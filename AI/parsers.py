"""
AI Response Parsers — JSON repair, score extraction, summary generation.

All parsing, repair, and extraction utilities for the ATS AI response
are centralised here so they can be maintained, tested, and debugged
independently from the AI service / Gemini call logic.
"""

import json
import logging
import re

logger = logging.getLogger("ai.parsers")


# ──────────────────────────────────────────────────────────────────────────────
# Scoring Helpers
# ──────────────────────────────────────────────────────────────────────────────

def apply_knockout_cap(rv: dict, score: int) -> int:
    """Apply knockout cap rules and return the adjusted score."""
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
    return score


def ensure_disposition(rv: dict, score: int) -> str:
    """Ensure pipeline_disposition is set based on score. Mutates *rv* in place."""
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
        rv["pipeline_disposition"] = disposition
    return disposition


# ──────────────────────────────────────────────────────────────────────────────
# Regex Fallback
# ──────────────────────────────────────────────────────────────────────────────

def extract_score_via_regex(text: str):
    """
    Last-resort regex extraction of match_score from raw text.
    Handles cases where JSON is truncated but the score field is present.
    Returns int score or None.
    """
    patterns = [
        r'"match_score"\s*:\s*(\d+)',
        r'"match_score"\s*:\s*"(\d+)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                return max(0, min(100, int(match.group(1))))
            except (ValueError, IndexError):
                continue
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Markdown Fence Cleanup
# ──────────────────────────────────────────────────────────────────────────────

def strip_markdown_fences(text: str) -> str:
    """Strip accidental ```json ... ``` markdown fences from raw AI output."""
    clean = text.strip()
    if clean.startswith("```json"):
        clean = clean[7:]
    if clean.startswith("```"):
        clean = clean[3:]
    if clean.endswith("```"):
        clean = clean[:-3]
    return clean.strip()


# ──────────────────────────────────────────────────────────────────────────────
# JSON Repair Utilities
# ──────────────────────────────────────────────────────────────────────────────

def _get_open_brackets(s: str) -> list:
    """Walk *s* and return a stack of unmatched open brackets/braces."""
    stack = []
    in_quote = False
    escaped = False
    for char in s:
        if escaped:
            escaped = False
            continue
        if char == '\\':
            escaped = True
            continue
        if char == '"':
            in_quote = not in_quote
            continue
        if in_quote:
            continue
        if char in ('[', '{'):
            stack.append(char)
        elif char in (']', '}'):
            if stack:
                top = stack[-1]
                if (char == ']' and top == '[') or (char == '}' and top == '{'):
                    stack.pop()
    return stack


def repair_truncated_json(json_str: str):
    """
    Attempt to repair truncated JSON strings by:
      1. Closing any open quote
      2. Cleaning trailing commas / colons / dangling keys
      3. Closing unmatched brackets / braces

    Returns the parsed dict on success, or None on failure.
    """
    json_str = json_str.strip()
    if not json_str:
        return None

    # 1. Close quote if open at the end
    in_quote = False
    escaped = False
    for char in json_str:
        if escaped:
            escaped = False
            continue
        if char == '\\':
            escaped = True
            continue
        if char == '"':
            in_quote = not in_quote

    repaired_str = json_str
    if in_quote:
        if repaired_str.endswith('\\'):
            repaired_str = repaired_str[:-1]
        repaired_str += '"'

    # 2. Clean up incomplete key-values, trailing commas/colons
    changed = True
    while changed:
        changed = False
        repaired_str = repaired_str.strip()

        if repaired_str.endswith(','):
            repaired_str = repaired_str[:-1].strip()
            changed = True
            continue

        if repaired_str.endswith(':'):
            repaired_str = repaired_str + ' null'
            changed = True
            continue

        if repaired_str.endswith('"'):
            last_quote_idx = repaired_str.rfind('"', 0, -1)
            if last_quote_idx != -1:
                prefix = repaired_str[:last_quote_idx].strip()
                if prefix.endswith(',') or prefix.endswith('{') or prefix.endswith('[') or not prefix:
                    repaired_str = prefix
                    changed = True
                    continue

    # 3. Close open brackets/braces
    stack = _get_open_brackets(repaired_str)
    repaired_list = list(repaired_str)
    while stack:
        top = stack.pop()
        if top == '{':
            repaired_list.append('}')
        elif top == '[':
            repaired_list.append(']')

    final_str = "".join(repaired_list)
    try:
        return json.loads(final_str)
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Main Response Parser
# ──────────────────────────────────────────────────────────────────────────────

def parse_ai_response(content: str):
    """
    Parse the ATS JSON response from Gemini.

    Returns ``(score, json_string)`` where *json_string* is always a
    re-serialised (valid) JSON string when possible.

    Strategy:
      1. Clean + direct ``json.loads``
      2. Repair truncated JSON and parse
      3. Regex fallback to at least extract the score
    """
    clean = strip_markdown_fences(content)

    # ── Strategy 1: Direct JSON parse ─────────────────────────────────────
    try:
        data = json.loads(clean)
        rv = data.get("recruiter_view", {})

        raw_score = rv.get("match_score", 0)
        score = max(0, min(100, int(raw_score)))
        score = apply_knockout_cap(rv, score)

        data["recruiter_view"]["match_score"] = score
        disposition = ensure_disposition(data["recruiter_view"], score)

        logger.info(
            f"[AI Parser] Score={score} | Disposition={disposition} "
            f"| Knockout={rv.get('knockout_applied', False)}"
        )
        return score, json.dumps(data)

    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.warning(f"[AI Parser] Direct JSON parse failed: {e}")

    # ── Strategy 2: Repair truncated JSON ─────────────────────────────────
    if clean.startswith("{"):
        repaired = repair_truncated_json(clean)
        if repaired and isinstance(repaired, dict):
            try:
                if "recruiter_view" not in repaired or not isinstance(
                    repaired.get("recruiter_view"), dict
                ):
                    repaired["recruiter_view"] = {}
                rv = repaired["recruiter_view"]

                raw_score = rv.get("match_score", 0)
                score = max(0, min(100, int(raw_score)))
                score = apply_knockout_cap(rv, score)
                repaired["recruiter_view"]["match_score"] = score
                disposition = ensure_disposition(repaired["recruiter_view"], score)

                logger.info(
                    f"[AI Parser - Repaired] Score={score} | Disposition={disposition}"
                )
                return score, json.dumps(repaired)
            except Exception as ex:
                logger.warning(f"[AI Parser] Error processing repaired JSON: {ex}")

    # ── Strategy 3: Regex fallback for score extraction ───────────────────
    regex_score = extract_score_via_regex(clean)
    if regex_score is not None and regex_score > 0:
        logger.info(
            f"[AI Parser - Regex Fallback] Extracted score={regex_score} from raw text"
        )
        fallback_data = {"recruiter_view": {"match_score": regex_score}}
        ensure_disposition(fallback_data["recruiter_view"], regex_score)
        # Still try to repair and merge for richer data
        if clean.startswith("{"):
            repaired = repair_truncated_json(clean)
            if repaired and isinstance(repaired, dict):
                repaired.setdefault("recruiter_view", {})["match_score"] = regex_score
                ensure_disposition(repaired["recruiter_view"], regex_score)
                return regex_score, json.dumps(repaired)
        return regex_score, json.dumps(fallback_data)

    logger.error(
        f"[AI Parser] All parsing strategies failed. Content preview: {clean[:200]}"
    )
    return 0, content


# ──────────────────────────────────────────────────────────────────────────────
# Summary Extraction
# ──────────────────────────────────────────────────────────────────────────────

def get_summary_from_dict(d: dict) -> str:
    """
    Extract a clean text summary from a structured evaluation dictionary.
    Falls back through multiple fields before constructing one manually.
    """
    if not isinstance(d, dict):
        return "No analysis available."

    recruiter_view = d.get("recruiter_view", {})
    intelligence = d.get("intelligence", {})

    # 1. Try recruiter view explanation
    explanation = recruiter_view.get("explanation", "")
    if explanation:
        return explanation

    # 2. Try AI recommendation reason (20-dim schema)
    rec_reason = recruiter_view.get("recommendation_reason", "")
    if rec_reason:
        return rec_reason

    # 3. Try recruiter view disposition rationale
    rationale = recruiter_view.get("disposition_rationale", "")
    if rationale:
        return rationale

    # 4. Try recruiter action memo
    action_memo = recruiter_view.get("recruiter_action_memo", "")
    if action_memo:
        return action_memo

    # 5. Try professional summary text (20-dim schema)
    prof_summary = intelligence.get("professional_summary", {})
    summary_text = prof_summary.get("summary_text", "")
    if summary_text:
        return summary_text

    # 6. Construct from parsed career details
    strengths = recruiter_view.get("strengths", [])
    career_summary = intelligence.get("career_summary", {})
    primary_role = career_summary.get("primary_role", "")
    years_exp = career_summary.get("total_years_experience", 0)
    company = career_summary.get("current_or_last_company", "")

    parts = []
    if primary_role:
        parts.append(f"Role: {primary_role}")
    if years_exp:
        parts.append(f"Experience: {years_exp} years")
    if company:
        parts.append(f"Company: {company}")

    if parts:
        summary = "Partial AI screening: " + ", ".join(parts)
        if strengths:
            summary += f". Key strengths: {', '.join(strengths[:3])}"
        summary += ". [Remaining analysis was truncated or incomplete.]"
        return summary

    return "AI screening completed with partial data."


def extract_summary_and_analysis(ai_analysis_str: str):
    """
    Extract explanation/summary **and** structured analysis dictionary
    from a potentially truncated JSON string.

    Returns ``(summary: str, analysis_dict: dict | None)``.
    """
    if not ai_analysis_str:
        return "No analysis available.", None

    clean = strip_markdown_fences(ai_analysis_str)

    # Strategy 1: Direct JSON parse
    try:
        analysis_dict = json.loads(clean)
        if isinstance(analysis_dict, dict):
            return get_summary_from_dict(analysis_dict), analysis_dict
    except Exception:
        pass

    # Strategy 2: Repair truncated / incomplete JSON
    if clean.startswith("{"):
        repaired_dict = repair_truncated_json(clean)
        if repaired_dict and isinstance(repaired_dict, dict):
            return get_summary_from_dict(repaired_dict), repaired_dict

    # Strategy 3: Plain text (error message or direct text response)
    if not clean.startswith("{"):
        summary = clean[:500] + "..." if len(clean) > 500 else clean
        return summary, None

    # All strategies failed — JSON-like but irreparable
    return (
        "Screening analysis was interrupted or formatted incorrectly. "
        "Please try re-running the screening.",
        None,
    )

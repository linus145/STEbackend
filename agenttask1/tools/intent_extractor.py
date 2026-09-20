import re
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

MONTH_NAMES_MAP = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12
}

PAYROLL_KEYWORDS = [
    "payroll", "salary", "salaries", "payslip", "payslips",
    "disbursement", "generate payroll", "run payroll", "process payroll",
    "calculate payroll", "monthly payroll"
]

AVAILABLE_TOOLS_REGISTRY = [
    {
        "id": "generate_monthly_payroll",
        "name": "Generate Monthly Payroll",
        "description": "Calculates attendance, leaves, taxes, deductions and compiles the monthly payroll draft.",
        "keywords": PAYROLL_KEYWORDS,
        "parameters": {
            "month": {"type": "integer", "description": "Month number (1-12)", "required": True},
            "year": {"type": "integer", "description": "4-digit year (e.g. 2026)", "required": True}
        }
    }
]


def extract_payroll_parameters(text: str) -> Tuple[Optional[int], Optional[int]]:
    """
    Deterministic rule-based extractor to pull month and year from user prompt.
    Zero LLM API call, 100% deterministic and instant.
    """
    clean_text = text.lower()
    
    # 1. Look for month names (e.g., 'September', 'Sep')
    extracted_month = None
    for name, month_num in MONTH_NAMES_MAP.items():
        # Match as whole word
        if re.search(rf"\b{name}\b", clean_text):
            extracted_month = month_num
            break

    # 2. Extract 4-digit year (e.g., 2024, 2025, 2026, 2027)
    extracted_year = None
    year_match = re.search(r"\b(20[2-3]\d)\b", clean_text)
    if year_match:
        extracted_year = int(year_match.group(1))

    # 3. If month was not found as name, check for numeric formats like '09/2026', '9-2026', or 'month 9'
    if not extracted_month:
        # Check MM/YYYY or MM-YYYY
        slash_match = re.search(r"\b(0?[1-9]|1[0-2])[\/\-](20[2-3]\d)\b", clean_text)
        if slash_match:
            extracted_month = int(slash_match.group(1))
            extracted_year = int(slash_match.group(2))
        else:
            # Check for 'month 9' or 'month: 9'
            month_label_match = re.search(r"\bmonth[:\s]+(0?[1-9]|1[0-2])\b", clean_text)
            if month_label_match:
                extracted_month = int(month_label_match.group(1))

    # Fallback year to current year if only month was specified
    if extracted_month and not extracted_year:
        extracted_year = datetime.now().year

    return extracted_month, extracted_year


def detect_tool_intent(user_input: str) -> Dict[str, Any]:
    """
    Classifies user intent deterministically without any external AI API.
    """
    if not user_input or not user_input.strip():
        return {
            "intent_detected": False,
            "tool_id": None,
            "parameters": {},
            "reason": "Empty user input"
        }

    clean_text = user_input.lower().strip()

    # Check for payroll intent
    is_payroll = any(kw in clean_text for kw in PAYROLL_KEYWORDS)
    if is_payroll:
        month, year = extract_payroll_parameters(clean_text)
        return {
            "intent_detected": True,
            "tool_id": "generate_monthly_payroll",
            "parameters": {
                "month": month,
                "year": year
            },
            "reason": "Matched payroll trigger keywords"
        }

    return {
        "intent_detected": False,
        "tool_id": None,
        "parameters": {},
        "reason": "No registered tool matched the input query"
    }

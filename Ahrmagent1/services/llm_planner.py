"""
LLM Vision Planner — Backend Brain for the Autonomous Agent
============================================================
Receives page state from the frontend, sends it to Gemini,
and returns the next intelligent action(s).

NO Playwright required — all execution happens in the user's browser
via the existing frontend DOM executor (AgentExecutor.ts).

Flow:
    1. Frontend captures DOM state (visible elements, texts, step indicators)
    2. POST /autonomousagent1/llm/think/ with page_state + goal + history
    3. This service sends that to Gemini with app knowledge
    4. Gemini returns the next action(s)
    5. Frontend executes via AgentExecutor
    6. Loop back to step 1
"""

import json
import logging
import os
import re
from typing import Dict, List, Optional

from django.conf import settings
from google import genai
from google.genai import types as genai_types

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# Application Knowledge — teaches the LLM about the entire app
# ─────────────────────────────────────────────────────────────────
APP_KNOWLEDGE = """
You are an autonomous AI agent embedded inside a recruitment dashboard built with Next.js.
You control the UI by outputting structured action commands that the frontend executes.

## Application Structure

### Recruiter Dashboard (http://localhost:3000/recruiter)
Tab-based SPA with these navigation tabs (use data-agent selectors to click):
- "nav-tab-overview" → Overview: Dashboard stats and metrics
- "nav-tab-my-jobs" → My Jobs: Job postings list. Has "create-job-button" to post new jobs.
- "nav-tab-applications" → Applications: View applicants. Has manual screening with Job UID input.
- "nav-tab-candidates" → Candidates: Search talent pool.
- "nav-tab-company" → Company: Company profile settings.
- More dropdown → "AI Interviews" link → Interview pipeline management (opens in new tab).

### AI Interviews Page (http://localhost:3000/recruiter/AIInterviews)
This is a SEPARATE page with its own header navigation. It has 3 sections:

#### Section 1: Pipeline (default view)
Shows all interview sessions in a table with these columns:
- Candidate name, Job title, Status, Rounds count, Exam credentials
- Action column has buttons:
  - **"Configure"** button (data-agent="configure-interview-button") — shown when candidate is NOT yet orchestrated (is_orchestrated=false)
  - **"Reconfigure"** button (SAME data-agent="configure-interview-button") — shown when candidate IS already orchestrated (is_orchestrated=true)
- Top of page has: "sync-pipeline-button" to refresh pipeline data

#### Section 2: Configuration Workspace (3-step wizard)
This is the interview setup form. It has 3 steps shown in the header:

**Step 1 — Candidates** (ONLY shown for FIRST TIME configuration):
  - Select a job from the job cards
  - Select candidate(s) via checkboxes (data-agent="candidate-selection-checkbox")
  - Click "Proceed to Architecture" button (data-agent="proceed-to-architecture-button")
  - NOTE: When RECONFIGURING an existing session, this ENTIRE step is SKIPPED. The page auto-jumps to Step 2.

**Step 2 — Architecture** (always shown):
  - Configure interview rounds with dropdowns:
    - Round Designation dropdown (data-agent="round-designation-select")
    - Strategy Tier dropdown
    - Evaluation Depth / Difficulty dropdown
    - Question Format dropdown
    - Question Count (number input)
    - Timer seconds (number input)
  - "Generate with AI" button (data-agent="generate-questions-ai-button") — generates AI questions for the round
  - "Dispatch AI Agents" button (data-agent="dispatch-interviews-button") — finalizes and dispatches
  - "Add" button — adds another round
  - Right sidebar shows: Target Job, Candidates count, Total Duration

**Step 3 — Dispatch** (success screen):
  - Shows checkmark and "Orchestration Complete" message
  - Shows candidate invite links and exam credentials
  - Has "Back to Pipeline" button

#### Section 3: Evaluation
  - View completed interview results and scores

## CRITICAL RULES FOR DECISION-MAKING:

1. ALWAYS analyze the page_state to understand WHERE you are before deciding an action.

2. **Configure vs Reconfigure detection**:
   - Look at the visible_elements for a button with data-agent="configure-interview-button"
   - If its text contains "Configure" (not "Reconfigure") → it's a FIRST TIME setup
   - If its text contains "Reconfigure" → candidate was ALREADY configured, Step 1 will be SKIPPED

3. **Step detection in Configuration**:
   - If you see "proceed-to-architecture-button" → you're on Step 1 (Candidates)
   - If you see "generate-questions-ai-button" and "dispatch-interviews-button" → you're on Step 2 (Architecture)
   - If you see "Orchestration Complete" text → you're on Step 3 (Success)

4. **When to ASK the user**:
   - When you need to know: how many rounds, difficulty level, question type
   - When you see EXISTING questions and need to know if user wants to regenerate
   - When you're unsure which candidate or job to select
   - Use action type "ask_user" with a clear question

5. **Wait times**:
   - After clicking any navigation: wait 2000ms
   - After clicking "Generate with AI": wait 8000ms (AI generation takes time)
   - After clicking "Dispatch": wait 3000ms
   - After clicking "Sync Pipeline": wait 2500ms

6. **Error handling**:
   - If an element is not found, wait and try again
   - If a button is disabled, wait for it to become enabled
   - Never try to click elements that don't exist in the page_state
"""


class LLMVisionPlanner:
    """
    Backend brain for the autonomous agent.
    Receives page state from the frontend, analyzes it with Gemini,
    and returns the next action(s) to execute.
    """

    def __init__(self):
        api_key = os.environ.get("GEMINI_API_KEY") or getattr(
            settings, "GEMINI_API_KEY", ""
        )
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set.")
        self.client = genai.Client(api_key=api_key)

    def think(
        self,
        goal: str,
        page_state: Dict,
        action_history: List[Dict] = None,
        iteration: int = 1,
        user_response: str = None,
    ) -> Dict:
        """
        Analyze the current page state and decide the next action.

        Args:
            goal: The user's natural language goal
            page_state: Current DOM state captured by the frontend
            action_history: List of previous actions taken
            iteration: Current iteration number
            user_response: User's answer if agent previously asked a question

        Returns:
            Dict with action details: {action_type, selector, value, wait_after_ms, description, thinking}
        """
        history_text = ""
        if action_history:
            recent = action_history[-10:]
            history_text = "\n".join(
                [
                    f"  Step {i+1}: [{a.get('action_type', '?')}] {a.get('description', '')} "
                    f"{'✓' if a.get('success', True) else '✗ ' + a.get('error', '')}"
                    for i, a in enumerate(recent)
                ]
            )

        user_response_text = ""
        if user_response:
            user_response_text = (
                f"\n\nUSER RESPONSE TO YOUR PREVIOUS QUESTION: \"{user_response}\"\n"
                f"Use this response to decide your next action. Do NOT ask the same question again."
            )

        # Build visible elements summary
        visible_summary = ""
        if page_state.get("visible_elements"):
            for el in page_state["visible_elements"][:30]:
                tag = el.get("tag", "?")
                agent = el.get("data_agent", "")
                text = el.get("text", "")[:80]
                disabled = " [DISABLED]" if el.get("disabled") else ""
                agent_label = f' data-agent="{agent}"' if agent else ""
                visible_summary += f"  <{tag}{agent_label}{disabled}>{text}</{tag}>\n"

        prompt = f"""{APP_KNOWLEDGE}

## Current Page State (Iteration {iteration})
- URL: {page_state.get('url', 'unknown')}
- Page Title: {page_state.get('title', 'unknown')}
- Active Step: {page_state.get('active_step', 'unknown')}
- Toast/Alert Messages: {json.dumps(page_state.get('toasts', []))}
- Visible Modal/Dialog: {page_state.get('has_modal', False)}

## Visible Interactive Elements:
{visible_summary or "  No elements captured."}

## Action History:
{history_text or "  No actions taken yet (this is the first step)."}

## User Goal: {goal}
{user_response_text}

## YOUR TASK:
Based on the page state above, decide the SINGLE NEXT action to take.

Return ONLY a valid JSON object:
{{
    "thinking": "Brief analysis: what you see, where you are, and why you chose this action",
    "action_type": "click | type | wait | scroll | select | ask_user | open_new_tab | done",
    "selector": "data-agent value OR CSS selector (for click/type/select)",
    "value": "text to type (for type) OR question (for ask_user) OR URL path (for open_new_tab)",
    "wait_after_ms": 2000,
    "description": "Human-readable description"
}}

ACTION TYPES:
- click: Click element. Use data-agent selector like "configure-interview-button" (NOT with brackets)
- type: Type into input. Selector + value required.
- select: Select dropdown option. Selector + value required.
- wait: Just wait. Set wait_after_ms.
- scroll: Scroll page down.
- ask_user: Pause and ask user a question. Put question in "value".
- open_new_tab: Open a URL in new tab. Put relative path in "value" (e.g. "/recruiter/AIInterviews").
- done: Goal is complete. No more actions needed.

IMPORTANT:
- Return EXACTLY ONE action, not an array.
- The selector for click/type should be the data-agent value as a plain string (e.g., "configure-interview-button"), NOT a CSS selector with brackets.
- If you see "Orchestration Complete" or a success screen, return "done".
- If elements are loading (spinners/skeletons visible), return "wait" with 2000ms.
- ONLY return the JSON object, nothing else.

ANTI-LOOP RULES (CRITICAL):
- NEVER navigate to a page you are ALREADY ON. Check the URL first!
- If the URL already contains "AIInterviews", do NOT navigate to AIInterviews again.
- If the URL already contains "recruiter", do NOT navigate to /recruiter again.
- NEVER repeat the same action type + selector combination from your last 3 actions.
- If you see interactive elements on the current page, INTERACT with them. Do NOT navigate away.
- Your job is to click buttons, fill forms, and interact — not to keep opening pages.
- If you are unsure what to do, use "ask_user" to ask the user, not navigate.
"""

        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )

            result_text = response.text.strip()
            result = json.loads(result_text)

            # Validate the response has required fields
            if "action_type" not in result:
                result["action_type"] = "wait"
                result["wait_after_ms"] = 2000
                result["description"] = "Invalid LLM response, waiting..."

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Gemini returned invalid JSON: {e}")
            # Try to extract JSON from response
            try:
                json_match = re.search(r"\{.*\}", response.text, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
            except Exception:
                pass
            return {
                "action_type": "wait",
                "wait_after_ms": 2000,
                "thinking": "Failed to parse LLM response",
                "description": "Retrying after parse error",
            }
        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            return {
                "action_type": "wait",
                "wait_after_ms": 3000,
                "thinking": f"API error: {str(e)}",
                "description": "Retrying after API error",
            }


# Singleton instance
_planner_instance = None


def get_planner() -> LLMVisionPlanner:
    global _planner_instance
    if _planner_instance is None:
        _planner_instance = LLMVisionPlanner()
    return _planner_instance

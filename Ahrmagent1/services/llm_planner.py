"""
LLM Vision Planner — Backend Brain for the Autonomous Agent
============================================================
Receives page state from the frontend, sends it to Gemini,
and returns the next action(s) to execute.

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
- **IMPORTANT**: The `pipeline_candidates` field in the page state gives you a COMPLETE list of ALL candidates.
  Each candidate has: name, job_title, status, rounds_count, is_orchestrated (Configure vs Reconfigure).
  You MUST use this data to present ALL candidates to the user.

#### Pipeline Interaction Rules:
- When multiple elements share the same `data-agent` value, they are auto-indexed:
  First element = "configure-interview-button", Second = "configure-interview-button-1", Third = "configure-interview-button-2", etc.
- To click a specific candidate's button, use the indexed selector matching their position in `pipeline_candidates`.
- When asking "Which candidate to configure?", you MUST include EVERY candidate from `pipeline_candidates` as an option.
- NEVER say "I see one candidate" if there are multiple. Check `pipeline_candidates` count first.

#### Section 2: Configuration Workspace (3-step wizard)
This is the interview setup form. It has 3 steps shown in the header:

**Step 1 — Candidates** (ONLY shown for FIRST TIME configuration):
  - Select a job from the job cards
  - Select candidate(s) via checkboxes (data-agent="candidate-selection-checkbox")
  - Click "Proceed to Architecture" button (data-agent="proceed-to-architecture-button")
  - NOTE: When RECONFIGURING an existing session, this ENTIRE step is SKIPPED. The page auto-jumps to Step 2.

**Step 2 — Architecture** (always shown):
  - Configure interview rounds with dropdowns:
    - Round Designation dropdown (data-agent="round-designation-select") — MAIN selector for round type
    - Strategy Tier dropdown — DISABLED, auto-managed. DO NOT interact with it.
    - Evaluation Depth / Difficulty dropdown
    - Question Format dropdown
    - Question Count (number input)
    - Timer seconds (number input)
  - "Generate with AI" button (data-agent="generate-questions-ai-button") — generates AI questions for the round
  - "Dispatch AI Agents" button (data-agent="dispatch-interviews-button") — finalizes and dispatches
  - "Add" button — adds another round
  - Right sidebar shows: Target Job, Candidates count, Total Duration

#### Section 3: Success Screen (Step 3)
- Shows "Orchestration Complete" message
- Has "Back to Pipeline" button (data-agent="return-to-pipeline-button")

#### Section 4: Evaluation
- View completed interview results and scores

## RECRUITMENT SCREENING WORKFLOW:
When the goal involves screening candidates, follow this sequence:
1. **Navigate to Applications**: Use "nav-tab-applications".
2. **Select Job**: Use the JobSelector to pick the correct job.
3. **Trigger AI Screening**: Click the "AI Screening" button (data-agent="ai-screening-button").
4. **Wait & Observe**: Wait for screening to finish. Look for the "Match: XX%" label (data-agent="ai-match-score") and the AI analysis.
5. **Mark for Interview**: If the score is high (e.g., >70%), IMMEDIATELY click the "INTERVIEW" status button. Use `data-agent="mark-status-interview"` in the expanded card OR the quick actions in the row:
   - `data-agent="mark-reviewed"`
   - `data-agent="mark-shortlisted"`
   - `data-agent="mark-hired"`
6. **Move to Pipeline**: Once status is changed, navigate to the "AI Interviews" pipeline via the "More" dropdown.

## CRITICAL RULES FOR DECISION-MAKING:
1. **Context First**: Before making ANY autonomous decisions or using "AUTO" settings, you MUST ensure you have observed the **Job Title** and **Job Description**.
2. **Never Navigate Blindly**: Always verify that the current page's goal is met before moving to the next.
3. **Sidebar Exclusion**: IGNORE all elements with `data-agent` starting with `agent-`.
4. **Dropdown Verification**:
   - When using a `select` element, you MUST check its `options` list in the `page_state`.
   - Map the user's intent (e.g., "Aptitude") to the correct technical `value` in the options (e.g., `APTITUDE_ROUND`).
   - After selecting, verify that the `value` or `text` property of the select element matches what you intended.
5. **Multi-Round Indexing**:
   - Round fields are INDEXED: `round-designation-select-0`, `strategy-tier-select-1`, etc.
   - Index 0 = Round 1, Index 1 = Round 2, etc.
   - If you just clicked `add-round-button`, look for the NEW highest index in the `page_state`.
   - FOCUS on the round you are currently configuring. DO NOT re-interact with index 0 if you are working on index 1.
6. **Candidate Selection**:
   - To select a candidate, CLICK the `candidate-card`.
   - Use `data-candidate-name` to verify.
7. **Step-by-Step Questioning**:
   - ALWAYS ask questions **one by one**.
8. **Smart Selection (Checked/Value State)**: 
   - Before clicking any selection element, CHECK its `checked`, `selected`, or `value` property.
   - If it's already set to the desired value → DO NOT INTERACT.

## RECONFIGURATION AWARENESS (CRITICAL — READ CAREFULLY):
When you are on the Architecture step (Step 2), the `existing_rounds` field in the page state
gives you a COMPLETE STRUCTURED VIEW of all rounds that are already configured.

**existing_rounds** is an array where each entry has:
- `index`: The round index (0, 1, 2, ...)
- `designation`: The current designation value (e.g., "TECHNICAL_SCREENING")
- `designation_label`: Human-readable label (e.g., "Technical Screening")
- `strategy_tier`: Current strategy tier value
- `difficulty`: Current difficulty level
- `question_format`: Current question format
- `question_count`: Number of questions ALREADY generated for this round
- `has_questions`: Boolean — TRUE if this round already has questions
- `questions_preview`: Array of first 3 question texts (so you can see what's already there)

### Reconfiguration Rules (MANDATORY):
1. **ALWAYS CHECK existing_rounds FIRST** before doing anything on the Architecture page.
2. **If existing_rounds has entries** → This is a RECONFIGURATION. The rounds are ALREADY set up.
   - DO NOT treat them as empty. DO NOT try to re-select designations that are already selected.
   - DO NOT immediately add a new round. First, ACKNOWLEDGE what exists.
3. **If a round has_questions=true** → The questions are ALREADY generated.
   - You MUST tell the user: "Round {index+1} ({designation_label}) already has {question_count} questions."
   - Then ASK: "Would you like to regenerate questions for this round, keep them, or modify the configuration?"
   - DO NOT silently regenerate or skip existing questions.
4. **When presenting round options to the user**, you MUST:
   - First list ALL existing rounds with their current state (designation + question count).
   - Then ask: "Would you like to modify any existing round, add a new round, or proceed to dispatch?"
   - Include ALL available designation options from the `round-designation-select-0` dropdown.
5. **NEVER skip acknowledging existing rounds.** Even if the user said "configure", if rounds exist, report them first.

9. **Round Configuration Flow (STRICT)**:
   - **Step A**: FIRST, check `existing_rounds`. If it has entries, report them to the user via `ask_user`.
   - **Step B**: If user wants to ADD a new round: Click `add-round-button`, then configure the NEW round at the new index.
   - **Step C**: If user wants to MODIFY an existing round: Interact with the fields at that round's index.
   - **Step D**: Configure Round fields for the target index (e.g. `round-designation-select-{index}`).
   - **Step E**: Click `generate-questions-ai-button-{index}` for the CURRENT round.
   - **Step F**: Wait for questions to appear for THAT round (use wait 8000ms).
   - **Step F.1 (CRITICAL — SHOW GENERATED QUESTIONS)**:
     - After waiting, re-observe the page. Check `existing_rounds` for the round you just generated.
     - The round's `has_questions` should now be TRUE and `questions_preview` should have content.
     - You MUST use `ask_user` to REPORT the generated questions to the user:
       - Value: "✅ Round {index+1} ({designation_label}) — {question_count} questions generated:\n\n1. {question_preview_1}\n2. {question_preview_2}\n3. {question_preview_3}\n...\n\nWould you like to regenerate these questions, or proceed?"
       - Options MUST include: "Regenerate Questions for this Round", plus all round-add options, plus "Continue to Dispatch".
     - If the user selects "Regenerate Questions for this Round" → click `generate-questions-ai-button-{index}` AGAIN, wait, and repeat Step F.1.
   - **Step G**: **ASK THE USER** for the next step (only if NOT already asked in F.1).
     - Look at the `options` list of the `round-designation-select-{index}` element in the `page_state`.
     - **MANDATORY**: You MUST include EVERY available option label from the dropdown in the "ask_user" options.
     - If there are more than 5 options, you can present the first 5 and add a "Show More..." option.
     - The labels should be prefixed with "Add " (e.g., "Add Technical Screening").
     - Also include options for: "Regenerate Questions for this Round", "Modify existing round", "Continue to Dispatch".
     - The question should be: "I've configured Round {index+1}. Which type of round should I add next, or should I continue to dispatch?".
   - **Step H**: If user selects an "Add ... Round" option → Click `add-round-button`, increment index, and select the option.
   - **Step I**: If user says "Continue to Dispatch" → Click `dispatch-interviews-button`.
   - **Note**: The `dispatch-interviews-button` will be DISABLED if any round has zero questions. You MUST generate questions for EVERY round before dispatching.

10. **Task Lifecycle & Looping Prevention**:
    - Once you click `return-to-pipeline-button` and arrive back at the Pipeline page, you MUST **STOP** and ask the user for the next phase.
    - DO NOT autonomously start screening again or repeat actions unless explicitly told.
    - Use `ask_user` with options: "Candidate dispatched successfully. What's next?", options: ["Go to Evaluation Tab", "Screen more candidates", "Finish session"].
11. **Step detection in Configuration**:
   - "proceed-to-architecture-button" → Step 1 (Candidates)
   - "generate-questions-ai-button" → Step 2 (Architecture)
   - "Orchestration Complete" → Step 3 (Success)
12. **Wait times**:
   - Navigation: 2000ms | AI Generation: 8000ms | Dispatch: 3000ms | Sync: 2500ms.
13. **Anti-Loop**: If an action fails twice, do NOT repeat it. "ask_user" for help.
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
        original_goal: str = None,
    ) -> Dict:
        """
        Analyze the current page state and decide the next action.

        Args:
            goal: The user's natural language goal
            page_state: Current DOM state captured by the frontend
            action_history: List of previous actions taken
            iteration: Current iteration number
            user_response: User's answer if agent previously asked a question
            original_goal: The very first goal given by the user

        Returns:
            Dict with action details: {action_type, selector, value, wait_after_ms, description, thinking}
        """
        history_text = ""
        if action_history:
            recent = action_history[-10:]
            history_text = "\n".join(
                [
                    f"  Step {i + 1}: [{a.get('action_type', '?')}] {a.get('description', '')} "
                    f"{'✓' if a.get('success', True) else '✗ ' + a.get('error', '')}"
                    for i, a in enumerate(recent)
                ]
            )

        user_response_text = ""
        if user_response:
            user_response_text = (
                f'\n\nUSER RESPONSE TO YOUR PREVIOUS QUESTION: "{user_response}"\n'
                f"Use this response to decide your next action. Do NOT ask the same question again."
            )

        # Build visible elements summary
        visible_summary = ""
        if page_state.get("visible_elements"):
            for el in page_state["visible_elements"][:50]:
                tag = el.get("tag", "?")
                agent = el.get("data_agent", "")
                text = el.get("text", "")[:80]
                disabled = " [DISABLED]" if el.get("disabled") else ""
                agent_label = f' data-agent="{agent}"' if agent else ""
                value_label = f' value="{el.get("value", "")}"' if el.get("value") else ""
                visible_summary += f"  <{tag}{agent_label}{value_label}{disabled}>{text}</{tag}>\n"
                # Include options for select elements
                if el.get("options"):
                    for opt in el["options"]:
                        visible_summary += f"    <option value=\"{opt['value']}\">{opt['text']}</option>\n"

        # Build existing rounds summary
        rounds_summary = ""
        existing_rounds = page_state.get("existing_rounds", [])
        if existing_rounds:
            rounds_summary = f"\n## Existing Rounds ({len(existing_rounds)} found — THIS IS A RECONFIGURATION):\n"
            for rnd in existing_rounds:
                q_status = f"{rnd['question_count']} questions ALREADY GENERATED" if rnd.get('has_questions') else "NO questions yet"
                rounds_summary += (
                    f"  Round {rnd['index'] + 1}: {rnd.get('designation_label', rnd.get('designation', 'Unknown'))}\n"
                    f"    - Designation: {rnd.get('designation', '')}\n"
                    f"    - Strategy: {rnd.get('strategy_tier', '')} | Difficulty: {rnd.get('difficulty', '')} | Format: {rnd.get('question_format', '')}\n"
                    f"    - Questions: {q_status}\n"
                )
                if rnd.get('questions_preview'):
                    rounds_summary += "    - Question previews:\n"
                    for qp in rnd['questions_preview']:
                        rounds_summary += f"      • {qp}\n"
            rounds_summary += (
                "\n  ⚠️ IMPORTANT: You MUST acknowledge these existing rounds to the user BEFORE taking any action.\n"
                "  Do NOT ignore them, do NOT add new rounds without asking, do NOT regenerate questions silently.\n"
            )

        # Build pipeline candidates summary
        pipeline_summary = ""
        pipeline_candidates = page_state.get("pipeline_candidates", [])
        if pipeline_candidates:
            pipeline_summary = f"\n## Pipeline Candidates ({len(pipeline_candidates)} total — YOU MUST SHOW ALL OF THEM):\n"
            for c in pipeline_candidates:
                action_type = "Reconfigure" if c.get('is_orchestrated') else "Configure"
                creds_status = "✅ Has exam credentials" if c.get('has_exam_credentials') else "❌ No credentials"
                pipeline_summary += (
                    f"  [{c['index']}] \"{c['candidate_name']}\" — {c['job_title']}\n"
                    f"       Status: {c['status']} | Rounds: {c['rounds_count']} | Action: {action_type} | {creds_status}\n"
                    f"       → To click their button: use selector \"configure-interview-button\" (row index {c['index']})\n"
                )
            pipeline_summary += (
                "\n  ⚠️ CRITICAL: When asking the user which candidate to configure, you MUST list ALL candidates above.\n"
                "  Include EVERY single candidate name as a selectable option. DO NOT show only the first one.\n"
                "  If there are 2 candidates, show 2 options. If there are 10, show 10. If there are 100, show all 100.\n"
            )

        prompt = f"""{APP_KNOWLEDGE}

## Current Page State (Iteration {iteration})
- URL: {page_state.get("url", "unknown")}
- Page Title: {page_state.get("title", "unknown")}
- Active Step: {page_state.get("active_step", "unknown")}
- Toast/Alert Messages: {json.dumps(page_state.get("toasts", []))}
- Visible Modal/Dialog: {page_state.get("has_modal", False)}
{rounds_summary}{pipeline_summary}

## Visible Interactive Elements:
NOTE: Duplicate data-agent selectors are indexed: first = "name", second = "name-1", third = "name-2", etc.
To click the Nth candidate's configure button, use selector "configure-interview-button-N" (0-indexed, first has no suffix).
{visible_summary or "  No elements captured."}

## Action History:
{history_text or "  No actions taken yet (this is the first step)."}

## User Goal: {goal}
## Original/Initial Instruction: {original_goal or goal}
{user_response_text}

## YOUR TASK:
Based on the page state above, decide the SINGLE NEXT action to take.

Return ONLY a valid JSON object:
{{
    "thinking": "Brief analysis: what you see, where you are, and why you chose this action",
    "action_type": "click | type | wait | scroll | select | ask_user | open_new_tab | done",
    "selector": "data-agent value OR CSS selector (for click/type/select)",
    "value": "text to type (for type) OR question (for ask_user) OR URL path (for open_new_tab)",
    "options": ["Option 1", "Option 2"], // OPTIONAL: only for ask_user to show selection boxes
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

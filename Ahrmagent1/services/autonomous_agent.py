import logging
import json
import re
import os
from typing import List, Dict
from datetime import datetime, timedelta
from django.conf import settings
from google import genai

logger = logging.getLogger(__name__)


class AutonomousAgentService:
    """
    Service for orchestrating internal application autonomy.
    Generates execution plans for the frontend agent.
    All navigation uses tab-click actions (data-agent selectors)
    since the recruiter dashboard is a single-page tab-based UI.
    """

    @staticmethod
    def _decompose_goal(user_goal: str) -> List[str]:
        """Uses Gemini to split a complex goal into discrete sub-goals."""
        api_key = os.environ.get("GEMINI_API_KEY") or getattr(
            settings, "GEMINI_API_KEY", ""
        )
        if not api_key:
            return [user_goal]

        try:
            client = genai.Client(api_key=api_key)
            prompt = f"""
            Analyze the following user goal for a recruitment AI agent: "{user_goal}"
            
            Determine if this request contains multiple distinct tasks that should be performed sequentially.
            Example: "post a senior and junior python job" -> ["Post Senior Python Developer job", "Post Junior Python Developer job"]
            
            Return a JSON object with a key "tasks" which is a list of strings. 
            If it's only one task, return a list with one item.
            """

            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=prompt,
                config={"response_mime_type": "application/json"},
            )
            data = json.loads(response.text)
            return data.get("tasks", [user_goal])
        except Exception as e:
            logger.error(f"Goal decomposition failed: {e}")
            return [user_goal]

    @staticmethod
    def _parse_continuation_intent(user_goal: str) -> List[Dict]:
        """Uses Gemini to intelligently parse the user's reconfiguration response."""
        api_key = os.environ.get("GEMINI_API_KEY") or getattr(
            settings, "GEMINI_API_KEY", ""
        )

        # Check if this is a confirmation for a multi-task plan
        # We look for the "Plan Summary:" marker we put in the ask_user message
        if "plan summary:" in user_goal.lower():
            # Isolate the user's actual reply to avoid "no" from "(yes/no)" prompt
            user_reply = user_goal.lower()
            if "user reply:" in user_reply:
                user_reply = user_reply.split("user reply:")[-1].strip()

            if any(
                kw in user_reply for kw in ["no", "don't", "stop", "cancel", "negative"]
            ):
                return [
                    {"type": "status", "message": "Task cancelled by user."},
                    {"type": "done"},
                ]

            # Extract the tasks from the goal string
            # Format was: "Plan Summary: 1. Goal A, 2. Goal B..."
            tasks = []
            # Use a more robust regex that handles newlines
            matches = re.findall(
                r"\d+\.\s*([\s\S]*?)(?=\s*\d+\.|\s*Is this correct|$)",
                user_goal,
                re.IGNORECASE,
            )
            if matches:
                # Clean up matches (remove trailing question parts)
                tasks = [m.split("Is this correct")[0].strip() for m in matches]

            if tasks:
                full_plan = [
                    {
                        "type": "status",
                        "message": f"Proceeding with {len(tasks)} confirmed tasks...",
                    }
                ]

                # Bulk generate all job data in one go to prevent sequential Gemini timeouts
                all_job_data = AutonomousAgentService._generate_multi_ai_job_data(tasks)

                for i, job_data in enumerate(all_job_data):
                    task_name = tasks[i]
                    full_plan.append(
                        {
                            "type": "status",
                            "message": f"Starting Task {i + 1}: {task_name}",
                        }
                    )

                    # Manual construction of plan steps to avoid re-calling Gemini inside the loop
                    job_plan = [
                        {"type": "wait", "duration": 2000},
                        {"type": "click", "selector": "nav-tab-my-jobs"},
                        {"type": "wait", "duration": 2500},
                        {"type": "click", "selector": "create-job-button"},
                        {"type": "wait", "duration": 2500},
                        {
                            "type": "type",
                            "selector": "job-title-input",
                            "value": job_data.get("title", "Developer"),
                        },
                        {"type": "wait", "duration": 2000},
                        {
                            "type": "type",
                            "selector": "job-description-input",
                            "value": job_data.get("description", ""),
                        },
                        {"type": "wait", "duration": 2000},
                        {
                            "type": "type",
                            "selector": "#job_type",
                            "value": job_data.get("job_type", "FULL_TIME"),
                        },
                        {"type": "wait", "duration": 2000},
                        {
                            "type": "type",
                            "selector": "#work_mode",
                            "value": job_data.get("work_mode", "REMOTE"),
                        },
                        {"type": "wait", "duration": 2000},
                        {
                            "type": "type",
                            "selector": "#experience_level",
                            "value": job_data.get("experience_level", "SENIOR"),
                        },
                        {"type": "wait", "duration": 2000},
                        {
                            "type": "type",
                            "selector": "#location",
                            "value": job_data.get("location", "Remote"),
                        },
                        {"type": "wait", "duration": 2000},
                        {
                            "type": "type",
                            "selector": "#department",
                            "value": job_data.get("department", "Engineering"),
                        },
                        {"type": "wait", "duration": 2000},
                        {
                            "type": "type",
                            "selector": "#salary_min",
                            "value": job_data.get("salary_min", ""),
                        },
                        {"type": "wait", "duration": 2000},
                        {
                            "type": "type",
                            "selector": "#salary_max",
                            "value": job_data.get("salary_max", ""),
                        },
                        {"type": "wait", "duration": 2000},
                        {
                            "type": "type",
                            "selector": "#currency",
                            "value": job_data.get("currency", "INR"),
                        },
                        {"type": "wait", "duration": 2000},
                        {
                            "type": "type",
                            "selector": "#open_positions",
                            "value": str(job_data.get("open_positions", "1")),
                        },
                        {"type": "wait", "duration": 2000},
                        {
                            "type": "type",
                            "selector": "#deadline",
                            "value": job_data.get("deadline", ""),
                        },
                        {"type": "wait", "duration": 2500},
                    ]

                    # Add Skills
                    skills = job_data.get("skills", [])
                    if skills:
                        job_plan.append(
                            {"type": "click", "selector": "skills-dropdown-trigger"}
                        )
                        job_plan.append({"type": "wait", "duration": 1500})
                        for skill in skills:
                            job_plan.append({"type": "click-skill", "value": skill})
                            job_plan.append({"type": "wait", "duration": 1000})
                        job_plan.append(
                            {"type": "click", "selector": "text='Skills Required *'"}
                        )
                        job_plan.append({"type": "wait", "duration": 1500})

                    job_plan.append({"type": "click", "selector": "submit-job-button"})
                    full_plan.extend(job_plan)

                return full_plan

        # Existing Interview Pipeline continuation logic
        plan = [
            {"type": "click", "selector": "configure-interview-button"},
            {"type": "wait", "duration": 2500},
            {"type": "status", "message": "Phase 5: Architecting rounds..."},
            {"type": "wait", "duration": 1500},
            # Optional: Reconfiguration jumps past this step automatically
            {
                "type": "click",
                "selector": "proceed-to-architecture-button",
                "optional": True,
            },
            {"type": "wait", "duration": 2500},
        ]

        if not api_key:
            # Fallback
            if not ("no " in user_goal.lower() or "don't" in user_goal.lower()):
                plan.extend(
                    [
                        {
                            "type": "status",
                            "message": "Phase 6: Generating AI questions...",
                        },
                        {"type": "click", "selector": "generate-questions-ai-button"},
                        {"type": "wait", "duration": 5000},
                    ]
                )
        else:
            try:
                client = genai.Client(api_key=api_key)
                prompt = f"""
                The autonomous AI agent paused execution to ask the recruiter: 
                "Candidate is already configured. Do you want to regenerate the AI questions?" OR "New candidate selected. How many rounds and what difficulty do you need?"
                
                The recruiter replied with: "{user_goal}"
                
                Analyze the recruiter's intent using natural language processing. Do they want the AI to generate/regenerate the technical interview questions?
                If they are just providing round names/difficulty without explicitly saying NO to generation, assume they want generation to occur.
                
                Return a JSON object with exactly one key: "should_generate_questions" with a boolean value (true or false).
                """

                response = client.models.generate_content(
                    model="gemini-2.5-flash-lite",
                    contents=prompt,
                    config={"response_mime_type": "application/json"},
                )
                data = json.loads(response.text)

                if data.get("should_generate_questions", True):
                    plan.extend(
                        [
                            {
                                "type": "status",
                                "message": "Phase 6: AI intent analysis confirmed generation is required...",
                            },
                            {
                                "type": "click",
                                "selector": "generate-questions-ai-button",
                            },
                            {"type": "wait", "duration": 5000},
                        ]
                    )
                else:
                    plan.append(
                        {
                            "type": "status",
                            "message": "Phase 6: AI intent analysis determined no regeneration needed. Skipping generation...",
                        }
                    )
            except Exception as e:
                logger.error(f"AI Intent Parsing failed: {e}")
                plan.extend(
                    [
                        {
                            "type": "status",
                            "message": "Phase 6: Generating AI questions (fallback)...",
                        },
                        {"type": "click", "selector": "generate-questions-ai-button"},
                        {"type": "wait", "duration": 5000},
                    ]
                )

        plan.extend(
            [
                {"type": "status", "message": "Phase 7: Final Dispatch..."},
                {"type": "click", "selector": "dispatch-interviews-button"},
                {"type": "wait", "duration": 3000},
                {
                    "type": "status",
                    "message": "End-to-End Recruitment Workflow Complete!",
                },
                {"type": "observe", "selector": "body"},
            ]
        )

        return plan

    @staticmethod
    def _generate_ai_job_data(goal_text: str) -> Dict:
        """
        Uses Gemini to generate rich job data based on the user's goal.
        """
        api_key = os.environ.get("GEMINI_API_KEY") or getattr(
            settings, "GEMINI_API_KEY", ""
        )

        # Calculate default one month deadline
        default_deadline = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

        if not api_key:
            return {
                "title": "Senior Full Stack Developer",
                "description": "We are looking for a skilled developer to build autonomous AI systems. Experience with React, Node.js, and LLMs is required.",
                "location": "Remote",
                "department": "Engineering",
                "salary_min": "120000",
                "salary_max": "180000",
                "job_type": "FULL_TIME",
                "work_mode": "REMOTE",
                "experience_level": "SENIOR",
                "open_positions": "1",
                "currency": "INR",
                "deadline": default_deadline,
                "skills": ["React", "Node.js", "TypeScript"],
            }

        try:
            client = genai.Client(api_key=api_key)
            prompt = f"""
            A recruiter wants to: {goal_text}
            Generate a highly professional and detailed job posting.
            
            STRICT RULES:
            ROLE:
You are an advanced AI Hiring Intelligence Engine responsible for generating precise, industry-accurate, seniority-aware technical skill requirements for jobs.

Your objective is to:
1. Understand the exact job title.
2. Detect the requested seniority level.
3. Generate ONLY relevant and realistic skills.
4. Avoid overengineering or hallucinating enterprise technologies.
5. Maintain consistency with real-world hiring standards.

==================================================
JOB TITLE ANALYSIS RULES
==================================================

1. Extract:
   - Primary Role
   - Technology Stack
   - Seniority Level
   - Domain (if mentioned)

2. Normalize titles:
   Examples:
   - "Laravel API Developer"
   → Backend Laravel Developer

   - "React Frontend Engineer"
   → Frontend React Engineer

   - "AI Python Engineer"
   → AI/ML Python Engineer

3. If seniority is missing:
   Default to MID-level expectations.

4. NEVER upgrade a role automatically to Senior/Lead.

==================================================
SENIORITY INTELLIGENCE RULES
==================================================

ENTRY / JUNIOR:
Focus on:
- Core syntax
- Framework fundamentals
- CRUD operations
- Basic debugging
- UI implementation
- Basic API usage
- Git basics
- Testing fundamentals

DO NOT include:
- System architecture
- Scalability
- Distributed systems
- Kubernetes
- Microservices
- Infrastructure ownership
- Team leadership

--------------------------------------------------

MID-LEVEL:
Focus on:
- Modular architecture
- API integrations
- Authentication systems
- Database optimization
- State management
- Reusable components
- Performance optimization
- Deployment understanding
- Unit/integration testing

Can include:
- Docker basics
- CI/CD basics
- Redis
- Queue systems

Avoid:
- Deep infrastructure ownership
- Enterprise distributed systems unless explicitly required

--------------------------------------------------

SENIOR / LEAD:
Focus on:
- System design
- Scalable architecture
- Security best practices
- Performance engineering
- Infrastructure patterns
- Caching strategy
- CI/CD architecture
- Cloud systems
- Observability
- Team mentoring
- Technical ownership

Can include:
- Kubernetes
- Terraform
- Event-driven systems
- Microservices
- High-scale architecture

ONLY include these if they realistically match the stack and role.

==================================================
SKILL GENERATION RULES
==================================================

Generate skills in the following categories:

1. PRIMARY_TECHNICAL_SKILLS
   Core technologies directly required for the role.

2. FRAMEWORKS_AND_LIBRARIES
   Relevant frameworks/tools.

3. DATABASES_AND_STORAGE

4. API_AND_INTEGRATION

5. DEVOPS_AND_DEPLOYMENT

6. TESTING_AND_QUALITY

7. ARCHITECTURE_AND_SCALABILITY
   Only for MID/SENIOR when relevant.

8. VERSION_CONTROL_AND_COLLABORATION

9. OPTIONAL_BONUS_SKILLS
   Nice-to-have only.

==================================================
ECOSYSTEM INTELLIGENCE RULES
==================================================

The AI MUST understand ecosystem-specific standards.

Example mappings:

Laravel:
- PHP
- Laravel
- Eloquent ORM
- REST API
- MySQL/PostgreSQL
- Authentication
- Queues
- Redis
- PHPUnit
- Laravel Sanctum/Passport

React:
- JavaScript/TypeScript
- React
- Hooks
- State Management
- API Integration
- Component Architecture
- Next.js
- Tailwind/Material UI
- Jest/Cypress

Django:
- Python
- Django
- DRF
- ORM
- PostgreSQL
- Authentication
- Celery
- Redis

Node.js:
- Node.js
- Express/NestJS
- JWT
- MongoDB/PostgreSQL
- WebSockets
- Queue systems

==================================================
ANTI-HALLUCINATION RULES
==================================================

1. NEVER include unrelated technologies.
2. NEVER force enterprise tools into small roles.
3. NEVER add cloud/devops skills unless relevant.
4. NEVER mix frontend and backend ecosystems incorrectly.
5. Avoid trendy buzzwords unless required by the role.

==================================================
OUTPUT QUALITY RULES
==================================================

1. Skills must be:
   - Realistic
   - Market-relevant
   - Seniority-correct
   - Stack-specific

2. Prefer precision over quantity.

3. Generate concise but complete skill sets.

4. Avoid duplicate or overlapping skills.

5. The final skill output must resemble a real-world ATS hiring requirement.

==================================================
FINAL OUTPUT FORMAT
==================================================

Return:
- Normalized Job Title
- Seniority Level
- Core Responsibilities
- Required Skills by Category
- Optional Skills
- Recommended Experience Indicators

The response must remain structured, deterministic, and ATS-friendly.
            
            Return ONLY a JSON object with these fields:
            - title: The job title.
            - description: A full, comprehensive job description in Markdown (500+ words). 
              Include sections for Role Overview, Key Responsibilities, Requirements, and Why Join Us.
            - location: A realistic location or 'Remote'.
            - department: The likely department (e.g., Engineering, Marketing).
            - salary_min: A realistic minimum yearly salary (number string).
            - salary_max: A realistic maximum yearly salary (number string).
            - currency: e.g. 'INR' or 'USD'.
            - open_positions: A number (1-10).
            - deadline: A date string (YYYY-MM-DD) which MUST BE {default_deadline}.
            - job_type: MUST BE one of [FULL_TIME, PART_TIME, CONTRACT, INTERNSHIP]
            - work_mode: MUST BE one of [REMOTE, ONSITE, HYBRID]
            - experience_level: MUST BE one of [ENTRY, MID, SENIOR, LEAD]. (Map 'Junior' to ENTRY or MID as appropriate).
            - skills: A list of 3 to 5 most relevant tech skills (e.g. ["Python", "AWS"]).
            """

            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=prompt,
                config={"response_mime_type": "application/json"},
            )
            data = json.loads(response.text)
            # Force deadline to be one month if AI hallucinates
            data["deadline"] = default_deadline
            return data
        except Exception as e:
            logger.error(f"AI Job Generation failed: {e}")
            return {
                "title": "Senior Developer",
                "description": f"We are looking for a candidate to help with: {goal_text}",
                "location": "Remote",
                "department": "Engineering",
                "job_type": "FULL_TIME",
                "work_mode": "REMOTE",
                "experience_level": "SENIOR",
                "open_positions": "1",
                "currency": "INR",
                "deadline": default_deadline,
                "skills": ["Software Engineering"],
            }

    @staticmethod
    def _generate_multi_ai_job_data(tasks: List[str]) -> List[Dict]:
        """Uses a single Gemini call to generate data for multiple jobs at once (prevents timeouts)."""
        api_key = os.environ.get("GEMINI_API_KEY") or getattr(
            settings, "GEMINI_API_KEY", ""
        )
        default_deadline = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

        if not api_key:
            return [AutonomousAgentService._generate_ai_job_data(t) for t in tasks]

        try:
            client = genai.Client(api_key=api_key)
            tasks_str = "\n".join([f"- {t}" for t in tasks])
            prompt = f"""
            Generate professional job postings for the following tasks:
            {tasks_str}
            
            STRICT RULES:
            1. For each job, use the EXACT seniority level mentioned (e.g. 'Junior', 'Lead', 'Senior').
            2. If NO level is mentioned for a task, do NOT default to 'Senior'. Default to a mid-level title.
            3. Ensure the title reflects the specific technology mentioned in the task.
            
            Return ONLY a JSON object with a key "jobs" containing a list of objects.
            Each object MUST have these fields:
            - title: The job title.
            - description: Comprehensive Markdown description (500+ words).
            - location: 'Remote' or city.
            - department: e.g. Engineering.
            - salary_min: Minimum salary (string).
            - salary_max: Maximum salary (string).
            - currency: 'INR' or 'USD'.
            - open_positions: Number.
            - deadline: MUST BE {default_deadline}.
            - job_type: [FULL_TIME, PART_TIME, CONTRACT, INTERNSHIP]
            - work_mode: [REMOTE, ONSITE, HYBRID]
            - experience_level: MUST BE one of [ENTRY, MID, SENIOR, LEAD]
            - skills: List of 3-5 tech skills.
            """

            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=prompt,
                config={"response_mime_type": "application/json"},
            )
            data = json.loads(response.text)
            jobs = data.get("jobs", [])

            # Ensure every task has a job entry, even if AI skipped some
            if len(jobs) < len(tasks):
                for i in range(len(jobs), len(tasks)):
                    jobs.append(AutonomousAgentService._generate_ai_job_data(tasks[i]))

            # Force deadline
            for job in jobs:
                job["deadline"] = default_deadline
            return jobs
        except Exception as e:
            logger.error(f"Multi-job generation failed: {e}")
            return [AutonomousAgentService._generate_ai_job_data(t) for t in tasks]

    @staticmethod
    def generate_plan(goal: Dict, skip_decompose: bool = False) -> List[Dict]:
        """
        Translates a natural language goal into a sequence of frontend actions.
        Uses tab switching (click) instead of URL navigation.
        """
        user_goal = goal.get("goal", "").lower()

        # Highest priority: Continuing a paused workflow (e.g., after ask_user)
        if "regarding my previous request" in user_goal:
            return AutonomousAgentService._parse_continuation_intent(user_goal)

        # Decompose goal if multi-tasking is detected
        if not skip_decompose:
            tasks = AutonomousAgentService._decompose_goal(user_goal)
            if len(tasks) > 1:
                summary = "\n".join([f"{i + 1}. {t}" for i, t in enumerate(tasks)])
                return [
                    {
                        "type": "status",
                        "message": "I've analyzed your request and identified multiple tasks.",
                    },
                    {
                        "type": "ask_user",
                        "message": f"I will perform the following actions sequentially:\n\nPlan Summary:\n{summary}\n\nIs this correct? (yes/no)",
                    },
                ]

        # Hire a developer workflow
        if "hire" in user_goal or "post" in user_goal or "job" in user_goal:
            if any(
                kw in user_goal
                for kw in [
                    "developer",
                    "engineer",
                    "designer",
                    "manager",
                    "hire",
                    "post",
                ]
            ):
                job_data = AutonomousAgentService._generate_ai_job_data(user_goal)

                plan = [
                    {"type": "wait", "duration": 2000},
                    {"type": "click", "selector": "nav-tab-my-jobs"},
                    {"type": "wait", "duration": 2500},
                    {"type": "click", "selector": "create-job-button"},
                    {"type": "wait", "duration": 2500},
                    {
                        "type": "type",
                        "selector": "job-title-input",
                        "value": job_data.get("title", "Senior Developer"),
                    },
                    {"type": "wait", "duration": 2000},
                    {
                        "type": "type",
                        "selector": "job-description-input",
                        "value": job_data.get("description", ""),
                    },
                    {"type": "wait", "duration": 2000},
                    {
                        "type": "type",
                        "selector": "#job_type",
                        "value": job_data.get("job_type", "FULL_TIME"),
                    },
                    {"type": "wait", "duration": 2000},
                    {
                        "type": "type",
                        "selector": "#work_mode",
                        "value": job_data.get("work_mode", "REMOTE"),
                    },
                    {"type": "wait", "duration": 2000},
                    {
                        "type": "type",
                        "selector": "#experience_level",
                        "value": job_data.get("experience_level", "SENIOR"),
                    },
                    {"type": "wait", "duration": 2000},
                    {
                        "type": "type",
                        "selector": "#location",
                        "value": job_data.get("location", "Remote"),
                    },
                    {"type": "wait", "duration": 2000},
                    {
                        "type": "type",
                        "selector": "#department",
                        "value": job_data.get("department", "Engineering"),
                    },
                    {"type": "wait", "duration": 2000},
                    {
                        "type": "type",
                        "selector": "#salary_min",
                        "value": job_data.get("salary_min", ""),
                    },
                    {"type": "wait", "duration": 2000},
                    {
                        "type": "type",
                        "selector": "#salary_max",
                        "value": job_data.get("salary_max", ""),
                    },
                    {"type": "wait", "duration": 2000},
                    {
                        "type": "type",
                        "selector": "#currency",
                        "value": job_data.get("currency", "INR"),
                    },
                    {"type": "wait", "duration": 2000},
                    {
                        "type": "type",
                        "selector": "#open_positions",
                        "value": str(job_data.get("open_positions", "1")),
                    },
                    {"type": "wait", "duration": 2000},
                    {
                        "type": "type",
                        "selector": "#deadline",
                        "value": job_data.get("deadline", ""),
                    },
                    {"type": "wait", "duration": 2500},
                ]

                # Add Skills Selection
                skills = job_data.get("skills", [])
                if skills:
                    # Use the stable data-agent selector for the trigger
                    plan.append(
                        {"type": "click", "selector": "skills-dropdown-trigger"}
                    )
                    plan.append({"type": "wait", "duration": 1500})

                    for skill in skills:
                        # The click-skill handler now handles searching and custom adding internally
                        # but we still provide steps for visual feedback in the stream
                        plan.append({"type": "click-skill", "value": skill})
                        plan.append({"type": "wait", "duration": 1000})

                    # Close dropdown
                    plan.append(
                        {"type": "click", "selector": "text='Skills Required *'"}
                    )
                    plan.append({"type": "wait", "duration": 1500})

                plan.append({"type": "click", "selector": "submit-job-button"})
                return plan

        # Find/search candidates workflow
        if any(
            kw in user_goal
            for kw in ["find", "search", "candidate", "talent", "shortlist"]
        ):
            return [
                {"type": "click", "selector": "nav-tab-candidates"},
                {"type": "wait", "duration": 800},
                {"type": "observe", "selector": "nav-tab-candidates"},
            ]

        # View applications workflow
        if any(kw in user_goal for kw in ["application", "applicant", "review"]):
            return [
                {"type": "click", "selector": "nav-tab-applications"},
                {"type": "wait", "duration": 800},
                {"type": "observe", "selector": "nav-tab-applications"},
            ]

        # View jobs workflow
        if any(kw in user_goal for kw in ["job", "posting", "vacancy"]):
            return [
                {"type": "click", "selector": "nav-tab-my-jobs"},
                {"type": "wait", "duration": 800},
                {"type": "observe", "selector": "nav-tab-my-jobs"},
            ]

        # Company profile workflow
        if any(kw in user_goal for kw in ["company", "profile"]):
            return [
                {"type": "click", "selector": "nav-tab-company"},
                {"type": "wait", "duration": 800},
                {"type": "observe", "selector": "nav-tab-company"},
            ]

        # Overview / dashboard
        if any(kw in user_goal for kw in ["overview", "dashboard", "stats"]):
            return [
                {"type": "click", "selector": "nav-tab-overview"},
                {"type": "wait", "duration": 800},
                {"type": "observe", "selector": "nav-tab-overview"},
            ]

        # Interview Orchestration / Pipeline workflow
        if any(
            kw in user_goal
            for kw in ["interview", "round", "orchestrate", "pipeline", "setup"]
        ):
            # Check for missing critical info
            missing_info = []
            if "round" not in user_goal and "setup" not in user_goal:
                missing_info.append("number of rounds")
            if not any(
                kw in user_goal for kw in ["technical", "hr", "coding", "behavioral"]
            ):
                missing_info.append("interview types (Technical, HR, etc.)")

            if missing_info:
                msg = f"I'm ready to set up the interview pipeline. Could you please specify the {', and '.join(missing_info)}?"
                return [
                    {"type": "ask_user", "message": msg, "context": "interview_setup"}
                ]

            is_coding = "coding" in user_goal
            
            # Initial navigation and setup steps
            plan = [
                {"type": "status", "message": "Navigating to Interview Pipeline..."},
                {"type": "click", "selector": "nav-more-button"},
                {"type": "wait", "duration": 1000},
                {"type": "click", "selector": "nav-link-interview-pipeline"},
                {"type": "wait", "duration": 3000},
                {"type": "status", "message": "Synchronizing pipeline data..."},
                {"type": "click", "selector": "sync-pipeline-button"},
                {"type": "wait", "duration": 2500},
                {"type": "status", "message": "Opening configuration workspace..."},
                {"type": "click", "selector": "configure-interview-button"},
                {"type": "wait", "duration": 2000},
                {
                    "type": "status",
                    "message": "Selecting candidates and configuring rounds...",
                },
                # For first-time config: select candidate. For reconfigure: this is optional
                {
                    "type": "click",
                    "selector": "candidate-selection-checkbox",
                    "optional": True,
                },
                {"type": "wait", "duration": 1500},
                # Step 1 is SKIPPED for reconfiguration — this button won't exist
                {
                    "type": "click",
                    "selector": "proceed-to-architecture-button",
                    "optional": True,
                },
                {"type": "wait", "duration": 2000},
            ]

            # Specialized logic for the Architecture phase - Suggest based on context
            if is_coding:
                # Ask user for specific configuration instead of assuming Python
                plan.append({
                    "type": "ask_user",
                    "message": "I've reached the Architecture step. Based on the job title/description, I recommend a Coding Round. Which programming language should I set up (Python, JavaScript, etc.), or would you prefer a different round type?",
                    "options": ["Setup Python Coding Round", "Setup JavaScript Coding Round", "Technical Screening Only", "Add More Rounds"]
                })
            else:
                # Standard verification for non-coding workflows
                plan.append({
                    "type": "ask_user",
                    "message": "I'm now in the Architecture step. Based on the role, should I add a Technical round or proceed to generate questions?",
                    "options": ["Add Technical Screening", "Add HR Round", "Generate Questions for current setup"]
                })
                
            return plan

        # Advanced Hiring Workflow / Autonomous Loop
        # Match if goal contains keywords OR just a raw UUID
        is_recruitment_goal = any(
            kw in user_goal
            for kw in [
                "full recruitment",
                "hiring loop",
                "autonomous hiring",
                "monitor",
                "screen",
                "hire",
            ]
        )
        uuid_match = re.search(r"([a-f0-9-]{32,})", user_goal)

        if is_recruitment_goal or uuid_match:
            job_id = uuid_match.group(1) if uuid_match else ""
            target_match = re.search(r"target:\s*(\d+)", user_goal) or re.search(
                r"(\d+)\s*applicants", user_goal
            )
            target_count = (
                int(target_match.group(1)) if target_match else 1
            )  # Default to 1 if just UID provided

            # Build the full continuous plan
            return [
                {
                    "type": "status",
                    "message": f"Phase 1: Starting autonomous screening for Job: {job_id}",
                },
                {"type": "click", "selector": "nav-tab-applications"},
                {"type": "wait", "duration": 2000},
                {"type": "type", "selector": "manual-job-uid-input", "value": job_id},
                {"type": "wait", "duration": 1500},
                {"type": "click", "selector": "manual-screen-button"},
                {"type": "wait", "duration": 3000},
                {
                    "type": "backend_call",
                    "task": "full_hiring_workflow",
                    "job_id": job_id,
                    "target_count": target_count,
                },
                {
                    "type": "status",
                    "message": "Phase 2: Waiting for AI selection to finalize winner...",
                },
                {
                    "type": "wait",
                    "duration": 8000,
                },  # Give backend time to finish pick-the-winner logic
                {
                    "type": "status",
                    "message": "Phase 3: Moving to Interview Pipeline for orchestration...",
                },
                # The agent opens the AI Interviews page in a new tab.
                # The frontend AgentController saves a cross-tab continuation goal.
                # In Tab 2, the LLM agent will automatically pick up and handle
                # interview configuration (sync → configure/reconfigure → generate → dispatch).
                {"type": "open_new_tab", "value": "/recruiter/AIInterviews"},
            ]

        # Default: observe the current page
        return [
            {"type": "observe", "selector": "body"},
        ]

    @staticmethod
    def execute_tool(tool_name: str, params: Dict) -> Dict:
        """
        Executes a backend tool.
        """
        logger.info(f"Executing tool: {tool_name} with params: {params}")
        return {"status": "success", "result": f"Executed {tool_name}"}

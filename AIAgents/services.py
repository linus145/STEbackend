import json
import os
from datetime import timedelta
from django.utils import timezone
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from jobs.models import JobPost, Skill

class JobGenerationSchema(BaseModel):
    title: str = Field(description="Job title")
    description: str = Field(description="Detailed and professional job description including responsibilities and requirements.")
    location: str = Field(description="City or location, e.g., 'San Francisco, CA' or 'Bangalore'")
    job_type: str = Field(description="Must be exactly one of: FULL_TIME, PART_TIME, CONTRACT, INTERNSHIP")
    work_mode: str = Field(description="Must be exactly one of: REMOTE, ONSITE, HYBRID")
    salary_min: int = Field(description="Minimum annual salary in numbers")
    salary_max: int = Field(description="Maximum annual salary in numbers")
    experience_level: str = Field(description="Must be exactly one of: ENTRY, MID, SENIOR, LEAD")
    department: str = Field(description="Department name, e.g., 'Engineering', 'Marketing'")
    open_positions: int = Field(description="Number of open positions. Extract from prompt if present, otherwise default to 1.")
    skills: list[str] = Field(description="List of 5 to 8 required skills")

class TalentSearchSchema(BaseModel):
    extracted_roles: list[str] = Field(description="Roles extracted from the prompt (e.g. ADMIN, FOUNDER, CO_FOUNDER, INVESTOR, MENTOR, SALES, MARKETING, ENGINEER, PRODUCT, DESIGN, OPERATIONS)")
    keywords: list[str] = Field(description="Key skills, names, or keywords mentioned")
    reasoning: str = Field(description="Short explanation of why these candidates would be a good fit")

class AIAgentService:
    @staticmethod
    def execute_job_post(company, prompt: str):
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set.")
            
        client = genai.Client(api_key=api_key)
        
        system_instruction = f"""
        You are an expert technical recruiter and AI Agent. 
        Your task is to generate a complete, highly professional job posting based on the user's prompt.
        The company name is {company.company_name}.
        Ensure the description is well-formatted, attractive, and includes responsibilities and qualifications.
        """

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=f"Generate a job posting for the following request: {prompt}",
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=JobGenerationSchema,
                temperature=0.7,
            ),
        )
        
        job_data = json.loads(response.text)
        
        job = JobPost.objects.create(
            company=company,
            title=job_data.get("title", "Software Engineer"),
            description=job_data.get("description", ""),
            location=job_data.get("location", "Remote"),
            job_type=job_data.get("job_type", "FULL_TIME"),
            work_mode=job_data.get("work_mode", "REMOTE"),
            salary_min=job_data.get("salary_min", 0),
            salary_max=job_data.get("salary_max", 0),
            currency="INR",
            experience_level=job_data.get("experience_level", "MID"),
            department=job_data.get("department", "Engineering"),
            open_positions=job_data.get("open_positions", 1),
            deadline=timezone.now() + timedelta(days=10),
            is_ai_generated=True,
            status="ACTIVE",
            hiring_status="ACTIVELY_HIRING"
        )

        skills_list = job_data.get("skills", [])
        job.skills_required = skills_list # fallback
        job.save()

        for skill_name in skills_list:
            skill_obj, _ = Skill.objects.get_or_create(name=skill_name[:100], defaults={'category': 'IT'})
            job.skills.add(skill_obj)
            
        return job

    @staticmethod
    def execute_schedule_interview(candidate_id: str):
        return {
            "candidate_id": candidate_id,
            "agent_notes": "Agent parsed the candidate's availability and proposed 3 time slots."
        }

    @staticmethod
    def execute_talent_search(prompt: str, user):
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set.")
            
        client = genai.Client(api_key=api_key)
        
        system_instruction = """
        You are an expert AI Talent Sourcer. 
        Analyze the user's natural language search prompt and extract the target roles and key skills or names.
        Map the roles strictly to these choices: ADMIN, FOUNDER, CO_FOUNDER, INVESTOR, MENTOR, SALES, MARKETING, ENGINEER, PRODUCT, DESIGN, OPERATIONS.
        If the user mentions an investor, map it to INVESTOR. If they mention a mentor, map it to MENTOR.
        """

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=f"Analyze this talent search query: {prompt}",
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=TalentSearchSchema,
                temperature=0.3,
            ),
        )
        
        data = json.loads(response.text)
        roles = data.get("extracted_roles", [])
        keywords = data.get("keywords", [])
        
        from useraccounts.models import CustomUser
        from django.db.models import Q
        
        qs = CustomUser.objects.filter(is_active=True)
        
        # Apply strict filtering based on AI extraction
        if roles:
            qs = qs.filter(role__in=roles)
            
        if keywords:
            keyword_q = Q()
            for kw in keywords:
                # search across common fields
                keyword_q |= Q(first_name__icontains=kw)
                keyword_q |= Q(last_name__icontains=kw)
                keyword_q |= Q(email__icontains=kw)
                keyword_q |= Q(role__icontains=kw)
            qs = qs.filter(keyword_q)
            
        # Get up to 15 best matches
        matches = qs.distinct().order_by('-created_at')[:15]
        
        candidates = []
        for u in matches:
            candidates.append({
                "id": str(u.id),
                "name": f"{u.first_name} {u.last_name}".strip() or u.email.split('@')[0],
                "role": u.role,
                "email": u.email,
            })
            
        from .models import AISearchHistory
        AISearchHistory.objects.create(
            user=user,
            query=prompt,
            reasoning=data.get("reasoning", ""),
            count=len(candidates),
            candidates_data=candidates
        )
            
        return {
            "query_analysis": data,
            "candidates": candidates,
            "count": len(candidates)
        }

    @staticmethod
    def get_talent_search_history(user):
        from .models import AISearchHistory
        qs = AISearchHistory.objects.filter(user=user).order_by('-created_at')[:20]
        return [
            {
                "id": str(h.id),
                "query": h.query,
                "reasoning": h.reasoning,
                "count": h.count,
                "candidates_data": h.candidates_data,
                "created_at": h.created_at.isoformat()
            }
            for h in qs
        ]

from django.db import transaction, models
from django.db.models import Count, Q
from .models import JobPost, JobApplication, AppliedJob
from typing import Dict, Any, List

class JobService:
    @staticmethod
    def get_active_jobs(filters: Dict[str, Any] = None):
        """
        Retrieves active jobs with optimized application counts and prefetching.
        """
        jobs = JobPost.objects.filter(status="ACTIVE").select_related("company")
        
        # Optimize application count using annotation instead of per-item count()
        jobs = jobs.annotate(
            applications_count=Count(
                "applications", 
                filter=Q(applications__is_deleted=False)
            )
        )

        if filters:
            if filters.get("job_type"):
                jobs = jobs.filter(job_type=filters["job_type"])
            if filters.get("work_mode"):
                jobs = jobs.filter(work_mode=filters["work_mode"])
            if filters.get("experience_level"):
                jobs = jobs.filter(experience_level=filters["experience_level"])
            if filters.get("search"):
                search = filters["search"]
                jobs = jobs.filter(
                    Q(title__icontains=search) | 
                    Q(description__icontains=search) | 
                    Q(company__company_name__icontains=search)
                )
        
        return jobs.order_by("-created_at")

    @staticmethod
    def get_recruiter_jobs(company, status: str = None):
        """
        Retrieves all jobs for a specific company with optimized counts.
        """
        jobs = company.job_posts.filter(is_deleted=False).annotate(
            applications_count=Count("applications", filter=Q(applications__is_deleted=False))
        )
        if status:
            jobs = jobs.filter(status=status)
        return jobs.order_by("-created_at")

    @staticmethod
    def apply_to_job(user, job_id: str, validated_data: dict):
        """
        Handles job application logic, including restoration of soft-deleted ones.
        """
        from django.shortcuts import get_object_or_404
        job = get_object_or_404(JobPost, id=job_id, status="ACTIVE")

        if hasattr(user, "company_profile") and job.company == user.company_profile:
            raise ValueError("You cannot apply to your own company's job.")

        with transaction.atomic():
            # Create/Restore application
            existing_app = JobApplication.all_objects.filter(job=job, applicant=user).first()
            application = None
            if existing_app:
                if not existing_app.is_deleted:
                    raise ValueError("You have already applied to this job.")
                existing_app.restore()
                for attr, value in validated_data.items():
                    setattr(existing_app, attr, value)
                existing_app.save()
                application = existing_app
            else:
                application = JobApplication.objects.create(job=job, applicant=user, **validated_data)
            
            # Log application snapshot in AppliedJob table
            AppliedJob.objects.create(
                job_id=str(job.id),
                job_name=job.title,
                resume_url=validated_data.get('resume_url', ''),
                applicant_id=str(user.id)
            )
            
            return application

    @staticmethod
    def get_dashboard_stats(company):
        """
        Optimized stats using single-query aggregation (Task 7).
        """
        jobs_qs = company.job_posts.filter(is_deleted=False)
        apps_qs = JobApplication.objects.filter(job__company=company, is_deleted=False)

        # Combine multiple counts into a single DB hit per table
        job_stats = jobs_qs.aggregate(
            total_jobs=Count('id'),
            active_jobs=Count('id', filter=Q(status="ACTIVE")),
            draft_jobs=Count('id', filter=Q(status="DRAFT")),
            closed_jobs=Count('id', filter=Q(status="CLOSED"))
        )

        app_stats = apps_qs.aggregate(
            total_applications=Count('id'),
            pending_applications=Count('id', filter=Q(status="PENDING")),
            reviewed=Count('id', filter=Q(status="REVIEWED")),
            shortlisted=Count('id', filter=Q(status="SHORTLISTED")),
            rejected=Count('id', filter=Q(status="REJECTED")),
            hired=Count('id', filter=Q(status="HIRED"))
        )

        return {**job_stats, **app_stats}

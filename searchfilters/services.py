from django.db.models import Q, Count
from jobs.models import JobPost, JobApplication
from posts.models import Post
from news.models import News
from useraccounts.models import CustomUser
from typing import Dict, Any


class SearchService:
    @staticmethod
    def search_jobs(filters: Dict[str, Any] = None):
        """
        Unified service for searching and filtering job posts.
        """
        queryset = JobPost.objects.filter(
            status="ACTIVE", is_deleted=False
        ).select_related("company")

        # Annotate application count
        queryset = queryset.annotate(
            applications_count=Count(
                "applications", filter=Q(applications__is_deleted=False)
            )
        )

        if not filters:
            return queryset.order_by("-created_at")

        # Basic text search
        search_query = filters.get("search")
        if search_query:
            queryset = queryset.filter(
                Q(title__icontains=search_query)
                | Q(description__icontains=search_query)
                | Q(company__company_name__icontains=search_query)
                | Q(location__icontains=search_query)
                | Q(skills__name__icontains=search_query)
                | Q(job_type__icontains=search_query)
                | Q(work_mode__icontains=search_query)
                | Q(experience_level__icontains=search_query)
                | Q(department__icontains=search_query)
            ).distinct()

        # Standard filters
        if filters.get("job_type"):
            queryset = queryset.filter(job_type=filters["job_type"])
        if filters.get("work_mode"):
            queryset = queryset.filter(work_mode=filters["work_mode"])
        if filters.get("experience_level"):
            queryset = queryset.filter(experience_level=filters["experience_level"])

        # Category mapping (Premium Dashboard Filters)
        category = filters.get("category")
        if category:
            if category == "IT":
                queryset = queryset.filter(skills__category="IT").distinct()
            elif category == "Non-IT":
                queryset = queryset.filter(skills__category="NON_IT").distinct()
            elif category == "Remote":
                queryset = queryset.filter(work_mode="REMOTE")
            elif category == "Full-time":
                queryset = queryset.filter(job_type="FULL_TIME")
            elif category == "Contract":
                queryset = queryset.filter(job_type="CONTRACT")
            elif category == "Internship":
                queryset = queryset.filter(job_type="INTERNSHIP")
            elif category == "Freelance":
                queryset = queryset.filter(job_type="CONTRACT")
            elif category == "B2_APPLY":
                queryset = queryset.filter(is_ai_generated=True)

        return queryset.order_by("-created_at")

    @staticmethod
    def search_applications(user, filters: Dict[str, Any] = None):
        """
        Unified service for searching and filtering a user's job applications.
        """
        queryset = JobApplication.objects.filter(
            applicant=user, is_deleted=False
        ).select_related("job", "job__company")

        if not filters:
            return queryset.order_by("-applied_at")

        # Basic text search (Job title or company name)
        search_query = filters.get("search")
        if search_query:
            queryset = queryset.filter(
                Q(job__title__icontains=search_query)
                | Q(job__company__company_name__icontains=search_query)
            )

        # Status filter
        status_filter = filters.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset.order_by("-applied_at")

    @staticmethod
    def search_social_posts(filters: Dict[str, Any] = None):
        """
        Service for searching public social posts.
        """
        queryset = Post.objects.filter(
            visibility="PUBLIC", is_deleted=False
        ).select_related("author")

        search_query = filters.get("search")
        if search_query:
            queryset = queryset.filter(content__icontains=search_query)

        return queryset.order_by("-created_at")

    @staticmethod
    def search_news(filters: Dict[str, Any] = None):
        """
        Service for searching news articles.
        """
        queryset = News.objects.filter(is_deleted=False).select_related("author")

        search_query = filters.get("search")
        if search_query:
            queryset = queryset.filter(
                Q(title__icontains=search_query) | Q(content__icontains=search_query)
            )

        return queryset.order_by("-created_at")

    @staticmethod
    def search_users(filters: Dict[str, Any] = None):
        """
        Service for searching other users/professionals.
        """
        queryset = CustomUser.objects.filter(is_active=True, is_deleted=False)

        search_query = filters.get("search")
        if search_query:
            queryset = queryset.filter(
                Q(first_name__icontains=search_query)
                | Q(last_name__icontains=search_query)
                | Q(email__icontains=search_query)
            )

        return queryset.order_by("-created_at")

    @classmethod
    def global_search(cls, filters: Dict[str, Any] = None):
        """
        Aggregated LinkedIn-style global search across multiple entities.
        """
        search_query = filters.get("search", "") if filters else ""
        limit = filters.get("limit", 5) if filters else 5

        return {
            "jobs": cls.search_jobs({"search": search_query})[:limit],
            "posts": cls.search_social_posts({"search": search_query})[:limit],
            "news": cls.search_news({"search": search_query})[:limit],
            "users": cls.search_users({"search": search_query})[:limit],
        }

    @staticmethod
    def filter_employees(queryset, filters: Dict[str, Any] = None):
        """
        Unified service in the searchfilters app for searching, filtering, and ordering employee querysets.
        """
        if not filters:
            return queryset.order_by("-created_at")

        # Basic text search
        search_query = filters.get("search")
        if search_query:
            queryset = queryset.filter(
                Q(first_name__icontains=search_query)
                | Q(last_name__icontains=search_query)
                | Q(email__icontains=search_query)
                | Q(employee_id__icontains=search_query)
            )

        # Standard filters
        if filters.get("status"):
            queryset = queryset.filter(status=filters["status"])
        if filters.get("employment_type"):
            queryset = queryset.filter(employment_type=filters["employment_type"])
        if filters.get("department"):
            queryset = queryset.filter(department_id=filters["department"])
        if filters.get("designation"):
            queryset = queryset.filter(designation_id=filters["designation"])

        # Date range
        joining_date__gte = filters.get("joining_date__gte")
        if joining_date__gte:
            queryset = queryset.filter(joining_date__gte=joining_date__gte)
        joining_date__lte = filters.get("joining_date__lte")
        if joining_date__lte:
            queryset = queryset.filter(joining_date__lte=joining_date__lte)

        # Ordering
        ordering = filters.get("ordering")
        if ordering:
            allowed_orderings = [
                "joining_date",
                "-joining_date",
                "created_at",
                "-created_at",
                "salary",
                "-salary",
            ]
            if ordering in allowed_orderings:
                queryset = queryset.order_by(ordering)
            else:
                queryset = queryset.order_by("-created_at")
        else:
            queryset = queryset.order_by("-created_at")

        return queryset

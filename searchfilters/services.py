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

        # Basic text search — split into individual keywords for precise matching
        search_query = filters.get("search")
        if search_query:
            keywords = search_query.strip().split()
            for keyword in keywords:
                queryset = queryset.filter(
                    Q(title__icontains=keyword)
                    | Q(description__icontains=keyword)
                    | Q(company__company_name__icontains=keyword)
                    | Q(location__icontains=keyword)
                    | Q(skills__name__icontains=keyword)
                    | Q(job_type__icontains=keyword)
                    | Q(work_mode__icontains=keyword)
                    | Q(experience_level__icontains=keyword)
                    | Q(department__icontains=keyword)
                )
            queryset = queryset.distinct()

        # Standard filters
        if filters.get("job_types"):
            queryset = queryset.filter(job_type__in=filters["job_types"])
        if filters.get("work_modes"):
            queryset = queryset.filter(work_mode__in=filters["work_modes"])
        if filters.get("experience_levels"):
            queryset = queryset.filter(experience_level__in=filters["experience_levels"])
        
        # Location filter
        location = filters.get("location")
        if location:
            queryset = queryset.filter(location__icontains=location)
            
        # Salary Range filters
        salary_min = filters.get("salary_min")
        if salary_min:
            try:
                queryset = queryset.filter(salary_max__gte=int(salary_min))
            except ValueError:
                pass
                
        salary_max = filters.get("salary_max")
        if salary_max:
            try:
                queryset = queryset.filter(salary_min__lte=int(salary_max))
            except ValueError:
                pass
                
        # Easy Apply filter
        if filters.get("easy_apply"):
            queryset = queryset.filter(is_ai_generated=True)

        # Posted Date filter
        posted_date = filters.get("posted_date")
        if posted_date:
            from django.utils import timezone
            from datetime import timedelta
            now = timezone.now()
            if posted_date == "24h":
                queryset = queryset.filter(created_at__gte=now - timedelta(days=1))
            elif posted_date == "week":
                queryset = queryset.filter(created_at__gte=now - timedelta(days=7))
            elif posted_date == "month":
                queryset = queryset.filter(created_at__gte=now - timedelta(days=30))

        # Category mapping (Premium Dashboard Filters)
        category = filters.get("category")
        if category:
            if category == "IT":
                queryset = queryset.filter(Q(skills__category="IT") | Q(job_category="IT")).distinct()
            elif category == "Non-IT":
                queryset = queryset.filter(Q(skills__category="NON_IT") | Q(job_category="NON_IT")).distinct()
            elif category == "Remote":
                queryset = queryset.filter(work_mode="REMOTE")
            elif category == "Hybrid":
                queryset = queryset.filter(work_mode="HYBRID")
            elif category == "On-site" or category == "Onsite":
                queryset = queryset.filter(work_mode="ONSITE")
            elif category == "Full-time":
                queryset = queryset.filter(job_type="FULL_TIME")
            elif category == "Part-time" or category == "Part-Time":
                queryset = queryset.filter(job_type="PART_TIME")
            elif category == "Contract":
                queryset = queryset.filter(job_type="CONTRACT")
            elif category == "Internship":
                queryset = queryset.filter(job_type="INTERNSHIP")
            elif category == "Freelance":
                queryset = queryset.filter(job_type="CONTRACT")
            elif category == "Entry Level" or category == "Entry":
                queryset = queryset.filter(experience_level="ENTRY")
            elif category == "Mid Level" or category == "Mid":
                queryset = queryset.filter(experience_level="MID")
            elif category == "Senior Level" or category == "Senior":
                queryset = queryset.filter(experience_level="SENIOR")
            elif category == "Lead":
                queryset = queryset.filter(experience_level="LEAD")
            elif category == "B2_APPLY":
                queryset = queryset.filter(is_ai_generated=True)

        return queryset.order_by("-created_at")

    @staticmethod
    def search_applications(user, filters: Dict[str, Any] = None):
        """
        Unified service for searching and filtering a user's job applications.
        """
        queryset = JobApplication.objects.filter(
            applicant=user, is_deleted=False, job__is_deleted=False
        ).select_related("job", "job__company")

        if not filters:
            return queryset.order_by("-applied_at")

        # Basic text search — split into keywords for precise matching
        search_query = filters.get("search")
        if search_query:
            keywords = search_query.strip().split()
            for keyword in keywords:
                queryset = queryset.filter(
                    Q(job__title__icontains=keyword)
                    | Q(job__company__company_name__icontains=keyword)
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
            keywords = search_query.strip().split()
            for keyword in keywords:
                queryset = queryset.filter(content__icontains=keyword)

        return queryset.order_by("-created_at")

    @staticmethod
    def search_news(filters: Dict[str, Any] = None):
        """
        Service for searching news articles.
        """
        queryset = News.objects.filter(is_deleted=False).select_related("author")

        search_query = filters.get("search")
        if search_query:
            keywords = search_query.strip().split()
            for keyword in keywords:
                queryset = queryset.filter(
                    Q(title__icontains=keyword) | Q(content__icontains=keyword)
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
            keywords = search_query.strip().split()
            for keyword in keywords:
                queryset = queryset.filter(
                    Q(first_name__icontains=keyword)
                    | Q(last_name__icontains=keyword)
                    | Q(email__icontains=keyword)
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
        if filters.get("role"):
            queryset = queryset.filter(role=filters["role"])

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

    @staticmethod
    def filter_payslips(queryset, filters: Dict[str, Any] = None):
        """
        Unified service in the searchfilters app for searching, filtering, and ordering payslip querysets.
        Supports: search (employee name/id), month, year, ordering.
        """
        if not filters:
            return queryset.order_by("-payroll__year", "-payroll__month")

        # Basic text search (employee name or ID)
        search_query = filters.get("search")
        if search_query:
            queryset = queryset.filter(
                Q(employee__first_name__icontains=search_query)
                | Q(employee__last_name__icontains=search_query)
                | Q(employee__email__icontains=search_query)
                | Q(employee__employee_id__icontains=search_query)
            )

        # Month filter (1-12)
        month = filters.get("month")
        if month:
            try:
                queryset = queryset.filter(payroll__month=int(month))
            except (ValueError, TypeError):
                pass

        # Year filter
        year = filters.get("year")
        if year:
            try:
                queryset = queryset.filter(payroll__year=int(year))
            except (ValueError, TypeError):
                pass

        # Ordering
        ordering = filters.get("ordering")
        if ordering:
            allowed_orderings = [
                "payroll__month",
                "-payroll__month",
                "payroll__year",
                "-payroll__year",
                "net_salary",
                "-net_salary",
                "created_at",
                "-created_at",
            ]
            if ordering in allowed_orderings:
                queryset = queryset.order_by(ordering)
            else:
                queryset = queryset.order_by("-payroll__year", "-payroll__month")
        else:
            queryset = queryset.order_by("-payroll__year", "-payroll__month")

        return queryset

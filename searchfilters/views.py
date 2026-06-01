from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.generics import ListAPIView

from .services import SearchService
from jobs.serializers import JobPostListSerializer, JobApplicationSerializer
from posts.serializers import PostSerializer
from news.serializers import NewsSerializer
from useraccounts.serializers import UserSerializer
from maincore.pagination import StandardResultsSetPagination


class ResponseMixin:
    def build_response(
        self, status_msg, message, data=None, status_code=status.HTTP_200_OK
    ):
        return Response(
            {
                "status": status_msg,
                "message": message,
                "data": data if data is not None else {},
            },
            status=status_code,
        )


class JobSearchView(ListAPIView, ResponseMixin):
    """
    GET: Search and filter public jobs.
    """

    permission_classes = (AllowAny,)
    serializer_class = JobPostListSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        filters = {
            "search": self.request.query_params.get("search"),
            "job_type": self.request.query_params.get("job_type"),
            "work_mode": self.request.query_params.get("work_mode"),
            "experience_level": self.request.query_params.get("experience_level"),
            "category": self.request.query_params.get("category"),
        }
        return SearchService.search_jobs(filters)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return self.build_response("success", "Jobs fetched.", serializer.data)


class DashboardJobSearchView(ListAPIView, ResponseMixin):
    """
    GET: Dedicated search for the Dashboard Jobs section.
    """
    permission_classes = (IsAuthenticated,)
    serializer_class = JobPostListSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        filters = {
            "search": self.request.query_params.get("search"),
            "category": self.request.query_params.get("category"),
        }
        return SearchService.search_jobs(filters)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return self.build_response("success", "Dashboard jobs fetched.", serializer.data)


class ApplicationSearchView(ListAPIView, ResponseMixin):
    """
    GET: Search and filter user's applications.
    """

    permission_classes = (IsAuthenticated,)
    serializer_class = JobApplicationSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        filters = {
            "search": self.request.query_params.get("search"),
            "status": self.request.query_params.get("status"),
        }
        return SearchService.search_applications(self.request.user, filters)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return self.build_response("success", "Applications fetched.", serializer.data)


class GlobalSearchView(APIView, ResponseMixin):
    """
    GET: Mixed results for jobs, posts, news, and users.
    """

    permission_classes = (AllowAny,)

    def get(self, request):
        search_query = request.query_params.get("search", "")
        limit = int(request.query_params.get("limit", 5))

        results = SearchService.global_search({"search": search_query, "limit": limit})

        data = {
            "jobs": JobPostListSerializer(results["jobs"], many=True).data,
            "posts": PostSerializer(results["posts"], many=True).data,
            "news": NewsSerializer(results["news"], many=True).data,
            "users": UserSerializer(results["users"], many=True).data,
        }

        return self.build_response("success", "Global search results fetched.", data)


class GlobalNewsSearchView(ListAPIView, ResponseMixin):
    """
    GET: Targeted global search for news articles.
    """

    permission_classes = (AllowAny,)
    serializer_class = NewsSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        filters = {"search": self.request.query_params.get("search")}
        return SearchService.search_news(filters)


class GlobalPostSearchView(ListAPIView, ResponseMixin):
    """
    GET: Targeted global search for social posts.
    """

    permission_classes = (AllowAny,)
    serializer_class = PostSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        filters = {"search": self.request.query_params.get("search")}
        return SearchService.search_social_posts(filters)


class GlobalUserSearchView(ListAPIView, ResponseMixin):
    """
    GET: Targeted global search for users/professionals.
    """

    permission_classes = (AllowAny,)
    serializer_class = UserSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        filters = {"search": self.request.query_params.get("search")}
        return SearchService.search_users(filters)


class PayslipSearchView(ListAPIView, ResponseMixin):
    """
    GET: Search and filter payslips by month, year, employee name/ID.
    Supports: ?search=&month=&year=&ordering=
    """

    permission_classes = (IsAuthenticated,)
    pagination_class = StandardResultsSetPagination

    def get_serializer_class(self):
        from payroll.serializers import PayslipSerializer
        return PayslipSerializer

    def get_queryset(self):
        from payroll.models import Payslip
        from payroll.views import get_active_startup

        startup = get_active_startup(self.request)
        if not startup:
            return Payslip.objects.none()

        base_qs = Payslip.objects.select_related(
            "employee", "payroll"
        ).filter(employee__startup=startup)

        # Security: non-admin employees can only see their own payslips
        is_admin_or_hr = (
            self.request.user.groups.filter(
                name__in=["Admin", "HR", "Payroll Manager"]
            ).exists()
            or self.request.user.is_superuser
            or hasattr(self.request.user, 'company_profile')
        )
        if not is_admin_or_hr:
            base_qs = base_qs.filter(
                employee__email=self.request.user.email, is_published=True
            )

        filters = {
            "search": self.request.query_params.get("search"),
            "month": self.request.query_params.get("month"),
            "year": self.request.query_params.get("year"),
            "ordering": self.request.query_params.get("ordering"),
        }
        return SearchService.filter_payslips(base_qs, filters)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return self.build_response("success", "Payslips fetched.", serializer.data)

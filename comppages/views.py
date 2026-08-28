import uuid
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils.text import slugify
from django.shortcuts import get_object_or_404
from django.db import transaction

from startups.models import CompanyProfile
from posts.models import Post
from posts.services import PostService
from maincore.imagekit_utils import ImageKitService
from jobs.models import JobPost
from .models import CompanyPage, CompanyPost
from .serializers import (
    CompanyPageDetailSerializer,
    CompanyPageCreateSerializer,
    CompanyPagePostSerializer,
    CompanyPageJobSerializer,
)


def get_or_create_page_for_company(company: CompanyProfile) -> CompanyPage:
    """Helper to ensure a CompanyProfile always has an associated CompanyPage."""
    page = CompanyPage.all_objects.filter(company=company).first()
    if page:
        if page.is_deleted:
            page.restore()
        return page

    # Auto-generate unique slug from company name
    slug = CompanyPage.generate_unique_slug(company.company_name)
    page = CompanyPage.objects.create(
        company=company,
        slug=slug,
        tagline=f"Empowering innovation at {company.company_name}",
        overview=company.description or "",
        is_verified=company.is_genuine,
    )
    return page


class UserCompanyCheckView(APIView):
    """
    GET /api/comppages/me/
    Checks if the authenticated user owns an existing company.
    If yes, returns has_company: True along with the full company page details and slug.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        if not request.user or not request.user.is_authenticated:
            return Response({"has_company": False, "authenticated": False})

        company = CompanyProfile.objects.filter(owner=request.user, is_deleted=False).first()
        if not company:
            return Response({"has_company": False, "authenticated": True})

        page = get_or_create_page_for_company(company)
        serializer = CompanyPageDetailSerializer(page, context={"request": request})
        return Response({
            "has_company": True,
            "authenticated": True,
            "company": serializer.data,
        })


class CompanyProfileView(APIView):
    """
    GET /api/comppages/<company_slug>/
    Retrieves full LinkedIn-style Company Profile by slug or UUID.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, company_slug):
        # 1. Try finding by page slug
        page = CompanyPage.objects.filter(slug=company_slug).select_related("company", "company__owner").first()
        
        # 2. If not found by slug, check if company_slug is a UUID
        if not page:
            try:
                val_uuid = uuid.UUID(company_slug)
                company = CompanyProfile.objects.filter(id=val_uuid, is_deleted=False).first()
                if company:
                    page = get_or_create_page_for_company(company)
            except ValueError:
                pass

        # 3. If still not found, search by company name slugify fallback
        if not page:
            company = CompanyProfile.objects.filter(company_name__iexact=company_slug.replace("-", " "), is_deleted=False).first()
            if company:
                page = get_or_create_page_for_company(company)

        if not page:
            return Response({"error": "Company page not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = CompanyPageDetailSerializer(page, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, company_slug):
        """Allow owner to update company page details."""
        if not request.user or not request.user.is_authenticated:
            return Response({"error": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)

        page = CompanyPage.objects.filter(slug=company_slug).select_related("company").first()
        if not page:
            return Response({"error": "Company page not found."}, status=status.HTTP_404_NOT_FOUND)

        if page.company.owner_id != request.user.id:
            return Response({"error": "You do not have permission to edit this company page."}, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        company = page.company

        # Update CompanyProfile core
        if "company_name" in data and data["company_name"]:
            company.company_name = data["company_name"]
        if "industry" in data:
            company.industry = data["industry"]
        if "company_size" in data:
            company.company_size = data["company_size"]
        if "description" in data:
            company.description = data["description"]
        if "website" in data:
            company.website = data["website"]
        if "location" in data:
            company.location = data["location"]
        if "founded_year" in data:
            company.founded_year = data["founded_year"]
        if "logo_url" in data:
            company.logo_url = data["logo_url"]
        if "banner_url" in data:
            company.banner_url = data["banner_url"]
        company.save()

        # Update CompanyPage
        if "tagline" in data:
            page.tagline = data["tagline"]
        if "page_type" in data:
            page.page_type = data["page_type"]
        if "overview" in data:
            page.overview = data["overview"]
        if "specialties" in data:
            page.specialties = data["specialties"]
        if "custom_logo_url" in data:
            page.custom_logo_url = data["custom_logo_url"]
        if "custom_banner_url" in data:
            page.custom_banner_url = data["custom_banner_url"]
        if "call_to_action_label" in data:
            page.call_to_action_label = data["call_to_action_label"]
        if "call_to_action_url" in data:
            page.call_to_action_url = data["call_to_action_url"]
        page.save()

        serializer = CompanyPageDetailSerializer(page, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class CompanyPageCreateView(APIView):
    """
    POST /api/comppages/create/
    Creates a new LinkedIn-style Company Page & Profile for authenticated users.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = CompanyPageCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        user = request.user

        # Check if user already has a company profile
        existing_company = CompanyProfile.objects.filter(owner=user, is_deleted=False).first()
        
        with transaction.atomic():
            if existing_company:
                company = existing_company
                company.company_name = data.get("company_name", company.company_name)
                company.industry = data.get("industry", company.industry)
                company.company_size = data.get("company_size", company.company_size)
                company.description = data.get("description", company.description)
                company.website = data.get("website", company.website)
                company.location = data.get("location", company.location)
                if data.get("founded_year"):
                    company.founded_year = data.get("founded_year")
                if data.get("logo_url"):
                    company.logo_url = data.get("logo_url")
                if data.get("banner_url"):
                    company.banner_url = data.get("banner_url")
                company.save()
            else:
                company = CompanyProfile.objects.create(
                    owner=user,
                    company_name=data["company_name"],
                    company_email=user.email,
                    industry=data.get("industry", "Technology"),
                    company_size=data.get("company_size", "1-10"),
                    description=data.get("description", ""),
                    website=data.get("website", ""),
                    location=data.get("location", ""),
                    founded_year=data.get("founded_year"),
                    logo_url=data.get("logo_url", ""),
                    banner_url=data.get("banner_url", ""),
                    is_approved=True,
                    is_genuine=True,
                )

            # Determine / generate slug
            custom_slug = data.get("slug")
            page = CompanyPage.all_objects.filter(company=company).first()
            if page and page.is_deleted:
                page.restore()

            if page:
                if custom_slug and custom_slug != page.slug:
                    page.slug = CompanyPage.generate_unique_slug(custom_slug, instance_id=page.id)
                page.tagline = data.get("tagline", page.tagline)
                page.page_type = data.get("page_type", page.page_type)
                page.overview = data.get("description", page.overview)
                page.specialties = data.get("specialties", page.specialties)
                page.custom_logo_url = data.get("logo_url", page.custom_logo_url)
                page.custom_banner_url = data.get("banner_url", page.custom_banner_url)
                page.call_to_action_label = data.get("call_to_action_label", page.call_to_action_label)
                page.call_to_action_url = data.get("call_to_action_url", page.call_to_action_url)
                page.save()
            else:
                final_slug = CompanyPage.generate_unique_slug(custom_slug or company.company_name)
                page = CompanyPage.objects.create(
                    company=company,
                    slug=final_slug,
                    tagline=data.get("tagline", f"Welcome to the official page of {company.company_name}"),
                    page_type=data.get("page_type", "COMPANY"),
                    overview=data.get("description", ""),
                    specialties=data.get("specialties", []),
                    custom_logo_url=data.get("logo_url", ""),
                    custom_banner_url=data.get("banner_url", ""),
                    call_to_action_label=data.get("call_to_action_label", "Visit website"),
                    call_to_action_url=data.get("call_to_action_url", company.website),
                    is_verified=True,
                )

        detail_serializer = CompanyPageDetailSerializer(page, context={"request": request})
        return Response(detail_serializer.data, status=status.HTTP_201_CREATED)


class CompanyPostsView(APIView):
    """
    GET /api/comppages/<company_slug>/posts/
    POST /api/comppages/<company_slug>/posts/
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, company_slug):
        page = get_object_or_404(CompanyPage, slug=company_slug)
        posts = CompanyPost.objects.filter(company_page=page).order_by("-created_at")[:20]
        serializer = CompanyPagePostSerializer(posts, many=True)
        return Response(serializer.data)

    def post(self, request, company_slug):
        if not request.user or not request.user.is_authenticated:
            return Response({"error": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)

        page = get_object_or_404(CompanyPage, slug=company_slug)
        if page.company.owner_id != request.user.id:
            return Response({"error": "Only the page admin can publish updates."}, status=status.HTTP_403_FORBIDDEN)

        content = request.data.get("content", "").strip()
        media_url = request.data.get("media_url", "")
        is_promoted = str(request.data.get("is_promoted", "false")).lower() in ("true", "1", "yes")

        # Handle direct file upload via ImageKit 3 (Company endpoint)
        uploaded_file = request.FILES.get("file") or request.FILES.get("image")
        if uploaded_file:
            upload_res = ImageKitService.upload_file(
                file_obj=uploaded_file,
                folder="/company_posts",
                file_name=uploaded_file.name,
                is_media_or_doc="company"
            )
            if upload_res and "url" in upload_res:
                media_url = upload_res["url"]

        if not content:
            return Response({"error": "Post content cannot be empty."}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Create in dedicated CompanyPost table
        post = CompanyPost.objects.create(
            author=request.user,
            company_page=page,
            content=content,
            media_url=media_url or None,
            is_promoted=is_promoted,
        )

        # 2. Sync to Post table so it appears seamlessly in the global Home Feed
        Post.objects.create(
            id=post.id,
            author=request.user,
            company_page=page,
            content=content,
            media_url=media_url or None,
            visibility="PUBLIC",
            is_promoted=is_promoted,
        )

        serializer = CompanyPagePostSerializer(post)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CompanyPostDetailView(APIView):
    """
    DELETE /api/comppages/<company_slug>/posts/<post_id>/
    Allows company page admin to delete a dedicated company post and its ImageKit image.
    """
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, company_slug, post_id):
        page = get_object_or_404(CompanyPage, slug=company_slug)
        if page.company.owner_id != request.user.id:
            return Response({"error": "Only the page admin can edit company updates."}, status=status.HTTP_403_FORBIDDEN)

        post = get_object_or_404(CompanyPost, id=post_id, company_page=page)
        content = request.data.get("content", "").strip()
        if not content:
            return Response({"error": "Post content cannot be empty."}, status=status.HTTP_400_BAD_REQUEST)

        post.content = content
        post.save(update_fields=["content", "updated_at"])
        Post.objects.filter(id=post_id).update(content=content)
        serializer = CompanyPagePostSerializer(post)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, company_slug, post_id):
        page = get_object_or_404(CompanyPage, slug=company_slug)
        if page.company.owner_id != request.user.id:
            return Response({"error": "Only the page admin can delete company updates."}, status=status.HTTP_403_FORBIDDEN)

        post = get_object_or_404(CompanyPost, id=post_id, company_page=page)
        if post.media_url:
            try:
                ImageKitService.delete_file(post.media_url)
            except Exception:
                pass
        post.delete()
        Post.objects.filter(id=post_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CompanyPostBoostView(APIView):
    """
    POST /api/comppages/<company_slug>/posts/<post_id>/boost/
    Allows company page owner to boost / promote an existing dedicated company post in the database.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, company_slug, post_id):
        page = get_object_or_404(CompanyPage, slug=company_slug)
        if page.company.owner_id != request.user.id:
            return Response({"error": "Only the page admin can boost company updates."}, status=status.HTTP_403_FORBIDDEN)

        post = get_object_or_404(CompanyPost, id=post_id, company_page=page)
        post.is_promoted = True
        post.save(update_fields=["is_promoted", "updated_at"])
        Post.objects.filter(id=post_id).update(is_promoted=True)
        serializer = CompanyPagePostSerializer(post)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CompanyJobsView(APIView):
    """
    GET /api/comppages/<company_slug>/jobs/
    List active job postings published by this company.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, company_slug):
        page = get_object_or_404(CompanyPage, slug=company_slug)
        jobs = JobPost.objects.filter(company=page.company, status="ACTIVE").order_by("-created_at")
        serializer = CompanyPageJobSerializer(jobs, many=True)
        return Response(serializer.data)


class ExploreCompaniesView(APIView):
    """
    GET /api/comppages/explore/
    List recommended / trending company pages for discovery.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        pages = CompanyPage.objects.select_related("company").all()[:12]
        serializer = CompanyPageDetailSerializer(pages, many=True, context={"request": request})
        return Response(serializer.data)

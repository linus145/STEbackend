from rest_framework.permissions import BasePermission


class IsCompanyOwner(BasePermission):
    """
    Allows access only to users who have a registered company profile.
    """

    message = "You must register a company profile before performing this action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return hasattr(request.user, "company_profile")


class IsJobOwner(BasePermission):
    """
    Object-level permission: only the company owner who posted the job
    can modify it or view its applications.
    """

    message = "You do not own this job post."

    def has_object_permission(self, request, view, obj):
        # obj could be a JobPost or a JobApplication
        if hasattr(obj, "company"):
            return obj.company.owner == request.user
        if hasattr(obj, "job"):
            return obj.job.company.owner == request.user
        return False

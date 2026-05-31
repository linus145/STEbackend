from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied

def check_subscription_feature(user, feature_name):
    """
    Check if the user has an active subscription that supports the specified feature.
    If the user is an employee, verify their company owner's subscription.
    """
    if not user or user.is_anonymous:
        return False

    owner = user
    if not hasattr(user, 'company_profile'):
        # Check if they are an employee
        employee = getattr(user, "employee_profile", None)
        if not employee:
            from employees.models import Employee
            employee = Employee.objects.filter(email=user.email).first()
        if employee and employee.organization and employee.organization.company:
            owner = employee.organization.company.owner

    try:
        from subscription.models import UserSubscription
        subscription = UserSubscription.objects.filter(user=owner, status="active").first()
        if not subscription:
            # Fallback to free plan features
            from subscription.models import SubscriptionPlan
            free_plan = SubscriptionPlan.objects.filter(plan_type="free").first()
            if free_plan:
                return getattr(free_plan, feature_name, False)
            return False
        
        if not subscription.plan:
            return False
            
        return getattr(subscription.plan, feature_name, False)
    except Exception:
        return False


class HasHRToolkitPermission(BasePermission):
    message = "This feature requires an active HRMS/Enterprise subscription plan."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        # Superusers bypass plan restrictions
        if request.user.is_superuser:
            return True
        return check_subscription_feature(request.user, "has_hr_toolkit")


class HasAIScreeningPermission(BasePermission):
    message = "This feature requires a Growth or Enterprise subscription plan."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return check_subscription_feature(request.user, "has_ai_resume_screening")


class HasAIInterviewPermission(BasePermission):
    message = "This feature requires a Growth or Enterprise subscription plan."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return check_subscription_feature(request.user, "has_ai_interview_pipeline")

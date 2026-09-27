from django.core.mail import send_mail
from django.conf import settings
from rest_framework.exceptions import PermissionDenied, AuthenticationFailed
from employees.models import Employee
from useraccounts.services import UserService

class EmployeeService:
    @staticmethod
    def authenticate_employee(username_or_email, password):
        """
        Pure logic for authenticating an employee under their company.
        Checks portal_username / email directly against Employee records and EmployeeUser,
        verifies credentials, and returns isolated EmployeeUser & JWT tokens.
        """
        from employees.models import Employee, EmployeeUser
        from django.db.models import Q
        from rest_framework_simplejwt.tokens import RefreshToken
        from django.utils import timezone
        
        # 1. Look up employee under company by portal_username OR email
        employee = Employee.objects.filter(
            Q(portal_username__iexact=username_or_email) | Q(email__iexact=username_or_email),
            is_deleted=False
        ).select_related('startup', 'organization').first()
        
        if not employee:
            raise AuthenticationFailed("Invalid employee credentials.")
            
        if employee.status in ['EXITED', 'INACTIVE']:
            raise PermissionDenied("This employee account is inactive. Please contact your HR administrator.")
            
        # 2. Get or create dedicated EmployeeUser
        emp_user = EmployeeUser.objects.filter(employee=employee).first()
        if not emp_user:
            emp_user = EmployeeUser.objects.create(
                employee=employee,
                portal_username=employee.portal_username,
                email=employee.email,
                role=employee.role,
                is_active=(employee.status not in ['EXITED', 'INACTIVE']),
            )
            if employee.portal_password:
                emp_user.set_password(employee.portal_password)
                emp_user.save()

        # 3. Validate password against EmployeeUser, employee.portal_password, or linked legacy user account
        is_valid = False
        if emp_user.check_password(password):
            is_valid = True
        elif employee.portal_password and employee.portal_password == password:
            is_valid = True
            emp_user.set_password(password)
            emp_user.save()
        elif employee.user and employee.user.check_password(password):
            is_valid = True
            emp_user.set_password(password)
            emp_user.save()
            
        if not is_valid:
            raise AuthenticationFailed("Invalid employee credentials.")

        # If employee was linked to a legacy shadow CustomUser, clean it up
        if employee.user and (employee.user.email.endswith('@employee.b2linq.local') or employee.user.email.startswith('emp_')):
            try:
                legacy_u = employee.user
                employee.user = None
                employee.save(update_fields=['user'])
                legacy_u.delete()
            except Exception:
                pass

        # Ensure latest synchronized attributes
        if emp_user.portal_username != employee.portal_username:
            emp_user.portal_username = employee.portal_username
        if emp_user.email != employee.email:
            emp_user.email = employee.email
        emp_user.role = employee.role
        emp_user.is_active = (employee.status not in ['EXITED', 'INACTIVE'])
        emp_user.last_login = timezone.now()
        emp_user.save()

        # 4. Generate SimpleJWT tokens directly for EmployeeUser without forcing CustomUser FK
        from rest_framework_simplejwt.settings import api_settings
        from rest_framework_simplejwt.utils import datetime_from_epoch
        refresh = RefreshToken()
        refresh[api_settings.USER_ID_CLAIM] = str(emp_user.id)
        refresh['user_type'] = 'employee'
        refresh['role'] = emp_user.role
        refresh['email'] = emp_user.email

        # If token_blacklist is active, register in OutstandingToken with user=None to prevent FK violation
        if "rest_framework_simplejwt.token_blacklist" in settings.INSTALLED_APPS:
            from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
            try:
                jti = refresh[api_settings.JTI_CLAIM]
                exp = refresh["exp"]
                OutstandingToken.objects.create(
                    user=None,
                    jti=jti,
                    token=str(refresh),
                    created_at=refresh.current_time,
                    expires_at=datetime_from_epoch(exp),
                )
            except Exception:
                pass

        tokens = {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }
        return emp_user, tokens

    @staticmethod
    def send_credentials_email(employee, host_meta=None, absolute_uri_fn=None, temp_password=None):
        """
        Pure logic for generating and sending credentials email to an employee.
        """
        login_url = "http://localhost:3000/employee/login"
        if host_meta:
            if 'localhost' not in host_meta and '127.0.0.1' not in host_meta and absolute_uri_fn:
                login_url = absolute_uri_fn('/employee/login').replace('api.', '')
                
        org_name = employee.organization.name if employee.organization else "B2linq"
        subject = f"Welcome to {org_name}, {employee.first_name}! Your Employee Portal Login"
        
        # Fallback text message
        pw_str = f"Temporary Password: {temp_password}" if temp_password else "Use the password provided by your HR operations manager, or request a reset."
        message = f"""Hello {employee.first_name} {employee.last_name},

Welcome to the team! Your portal login account has been initialized.

You can now log in to the {org_name} Employee Hub to view your attendance logs, submit check-ins/outs, and post leave requests.

Employee Portal Link: {login_url}
Username (Portal Username): {employee.portal_username}
{pw_str}

If you need to change your login credentials, you can securely do so directly in the portal dashboard header.

Best Regards,
HR Operations Team
"""
        from django.template.loader import render_to_string
        context = {
            "first_name": employee.first_name,
            "last_name": employee.last_name,
            "portal_username": employee.portal_username,
            "login_url": login_url,
            "temp_password": temp_password,
            "company_name": org_name,
        }
        
        html_message = render_to_string("emails/credentials_invite.html", context)
        
        email_sent = False
        from_email_addr = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@b2linq.com')
        from_email_formatted = f"{org_name} <{from_email_addr}>"
        try:
            from useraccounts.tasks import send_email_async
            send_email_async.delay(
                subject=subject,
                message=message,
                recipient_list=[employee.email],
                from_email=from_email_formatted,
                html_message=html_message
            )
            email_sent = True
        except Exception as e:
            try:
                from django.core.mail import send_mail
                send_mail(
                    subject,
                    message,
                    from_email_formatted,
                    [employee.email],
                    fail_silently=False,
                    html_message=html_message,
                )
                email_sent = True
            except Exception as direct_err:
                print(f"Direct send_mail also failed: {direct_err}")
            
        return {
            "email": employee.email,
            "portal_username": employee.portal_username,
            "login_url": login_url,
            "sent": email_sent
        }

    @staticmethod
    def change_credentials(employee, user, portal_username=None, password=None):
        """
        Pure logic for changing employee credentials (username and/or password).
        """
        from employees.models import Employee, EmployeeUser
        from rest_framework.exceptions import ValidationError

        if portal_username:
            new_username = portal_username.strip().lower()
            if not new_username:
                raise ValidationError("Username cannot be empty.")
            # Validate uniqueness across both Employee and EmployeeUser
            if Employee.all_objects.filter(portal_username=new_username).exclude(id=employee.id).exists():
                raise ValidationError("Username already taken by another employee. Please choose a different username.")
            if EmployeeUser.objects.filter(portal_username=new_username).exclude(employee=employee).exists():
                raise ValidationError("Username already taken by another employee. Please choose a different username.")
            employee.portal_username = new_username
            employee.save(update_fields=['portal_username'])
            
        if password:
            employee.portal_password = password
            employee.save(update_fields=['portal_password'])

        # Update dedicated EmployeeUser
        emp_user = EmployeeUser.objects.filter(employee=employee).first()
        if not emp_user:
            emp_user = EmployeeUser.objects.create(
                employee=employee,
                portal_username=employee.portal_username,
                email=employee.email,
                role=employee.role,
                is_active=(employee.status not in ['EXITED', 'INACTIVE']),
            )
        if portal_username:
            emp_user.portal_username = employee.portal_username
        if password:
            emp_user.set_password(password)
        emp_user.save()

        # If user passed is a legacy CustomUser, synchronize it too
        if user and user != emp_user and hasattr(user, 'set_password'):
            if password:
                user.set_password(password)
                user.save()
            
        return employee.portal_username

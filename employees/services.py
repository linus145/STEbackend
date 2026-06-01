from django.core.mail import send_mail
from django.conf import settings
from rest_framework.exceptions import PermissionDenied, AuthenticationFailed
from employees.models import Employee
from useraccounts.services import UserService

class EmployeeService:
    @staticmethod
    def authenticate_employee(username_or_email, password):
        """
        Pure logic for authenticating an employee.
        Checks portal_username / email, verifies that the user is an active employee,
        and returns the user & JWT tokens.

        NOTE: Email verification (is_verified) is intentionally NOT checked here.
        Employee accounts are provisioned directly by HR admins — they do not go
        through the self-registration OTP flow that normal platform users follow.
        """
        user = UserService.authenticate_user(username_or_email, password)
        if not user:
            raise AuthenticationFailed("Invalid employee credentials.")

        if not hasattr(user, 'employee_profile'):
            raise PermissionDenied("This account is not registered as an employee.")

        tokens = UserService.generate_tokens(user)
        return user, tokens

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
        try:
            from useraccounts.tasks import send_email_async
            from_email_addr = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@b2linq.com')
            from_email_formatted = f"{org_name} <{from_email_addr}>"
            send_email_async.delay(
                subject=subject,
                message=message,
                recipient_list=[employee.email],
                from_email=from_email_formatted,
                html_message=html_message
            )
            email_sent = True
        except Exception as e:
            print(f"Failed to queue Celery email task: {e}")
            
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
        if portal_username:
            new_username = portal_username.strip().lower()
            if not new_username:
                raise ValidationError("Username cannot be empty.")
            # Validate uniqueness
            if Employee.all_objects.filter(portal_username=new_username).exclude(id=employee.id).exists():
                raise ValidationError("Username already taken by another employee. Please choose a different username.")
            employee.portal_username = new_username
            employee.save()
            
        if password:
            user.set_password(password)
            user.save()
            
        return employee.portal_username

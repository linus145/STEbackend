from django.core.mail import send_mail
from django.conf import settings
from rest_framework.exceptions import ValidationError, PermissionDenied, AuthenticationFailed
from employees.models import Employee
from useraccounts.services import UserService

class EmployeeService:
    @staticmethod
    def authenticate_employee(username_or_email, password):
        """
        Pure logic for authenticating an employee.
        Checks portal_username / email, verifies that the user is an active employee,
        checks email verification, and returns the user & JWT tokens.
        """
        user = UserService.authenticate_user(username_or_email, password)
        if not user:
            raise AuthenticationFailed("Invalid employee credentials.")
            
        if not hasattr(user, 'employee_profile'):
            raise PermissionDenied("This account is not registered as an employee.")
            
        if not user.is_verified:
            raise ValidationError({
                "error": "Email not verified. Please verify your email using OTP.",
                "email": user.email,
                "is_verified": False
            })
            
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
                
        subject = f"Welcome to B2linq, {employee.first_name}! Your Employee Portal Login"
        
        # Fallback text message
        pw_str = f"Temporary Password: {temp_password}" if temp_password else "Use the password provided by your HR operations manager, or request a reset."
        message = f"""Hello {employee.first_name} {employee.last_name},

Welcome to the team! Your portal login account has been initialized.

You can now log in to the B2linq Employee Hub to view your attendance logs, submit check-ins/outs, and post leave requests.

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
        }
        
        html_message = render_to_string("emails/credentials_invite.html", context)
        
        email_sent = False
        try:
            send_mail(
                subject,
                message,
                getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@b2linq.com'),
                [employee.email],
                fail_silently=False,
                html_message=html_message
            )
            email_sent = True
        except Exception as e:
            print(f"SMTP Error: {e}")
            
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

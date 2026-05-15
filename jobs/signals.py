import uuid
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from .models import JobApplication
from employees.models import Employee, EmployeeProfile, EmployeeDocument
from organization.models import Organization, Department, Designation
from startups.models import Startup, CompanyProfile

logger = logging.getLogger(__name__)


@receiver(post_save, sender=JobApplication)
def handle_employee_sync_on_status_change(sender, instance, created, **kwargs):
    """
    Manages the Employee record based on JobApplication status.
    - 'HIRED': Creates or restores the Employee record.
    - Other status: Deletes the Employee record if it was previously created from this application.
    """
    try:
        # Case 1: Status is HIRED -> Create/Update Employee
        if instance.status == "HIRED":
            applicant = instance.applicant
            job = instance.job
            company_profile = job.company

            # 1. Get or Create Organization
            organization = Organization.objects.filter(company=company_profile).first()
            if not organization:
                organization = Organization.objects.create(
                    company=company_profile,
                    name=company_profile.company_name,
                    address=company_profile.location,
                    website=company_profile.website,
                )

            # 2. Find related startup
            startup = Startup.objects.filter(founder=company_profile.owner).first()

            # 3. Get or Create Employee
            # Map internship to the correct choice in Employee model
            type_map = {
                "FULL_TIME": "FULL_TIME",
                "CONTRACT": "CONTRACT",
                "INTERNSHIP": "INTERN",
            }
            emp_type = type_map.get(instance.employment_type, "FULL_TIME")

            employee, emp_created = Employee.objects.get_or_create(
                job_application=instance,
                defaults={
                    "startup": startup,
                    "organization": organization,
                    "user": applicant,
                    "employee_id": f"EMP-{uuid.uuid4().hex[:6].upper()}",
                    "first_name": applicant.first_name or "New",
                    "last_name": applicant.last_name or "Employee",
                    "email": applicant.email,
                    "joining_date": timezone.now().date(),
                    "employment_type": emp_type,
                    "status": "ON_BOARDING",
                    "avatar": company_profile.logo_url,
                },
            )

            if emp_created:
                # 4. Create Profile Details
                EmployeeProfile.objects.get_or_create(
                    employee=employee, defaults={"personal_email": applicant.email}
                )

                # 5. Create Document from Resume
                if instance.resume_url:
                    EmployeeDocument.objects.get_or_create(
                        employee=employee,
                        document_name="Application Resume",
                        defaults={
                            "document_type": "RESUME",
                            "file_url": instance.resume_url,
                        },
                    )
                logger.info(f"Created Employee for {applicant.email}")
            else:
                # Ensure existing employee is linked correctly and active
                employee.is_deleted = False
                employee.save()

        # Case 2: Status is NOT HIRED -> Remove Employee if exists
        else:
            # Look for an employee linked to this application
            employee = getattr(instance, "hired_employee", None)
            if employee:
                logger.info(
                    f"Removing Employee record as application status changed to {instance.status}"
                )
                # We can either delete or soft-delete. User said "not going back",
                # so we should remove it from the view.
                employee.delete()

    except Exception as e:
        logger.error(f"Error in handle_employee_sync signal: {str(e)}")

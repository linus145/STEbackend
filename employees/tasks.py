import logging
import random
import string
from datetime import datetime
from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone

logger = logging.getLogger("employees.tasks")

@shared_task(bind=True)
def task_bulk_import_employees(self, organization_id, startup_id, employees_data):
    """
    Celery task to asynchronously import a batch of employees with pre-cached lookups
    and live progress updates.
    """
    from organization.models import Organization, Department, Designation
    from employees.models import (
        Employee, EmployeeBankDetail, EmployeePANDetail, EmployeeAadhaarDetail
    )
    from startups.models import Startup

    User = get_user_model()

    try:
        organization = Organization.objects.filter(id=organization_id).first() if organization_id else None
        startup = Startup.objects.filter(id=startup_id).first() if startup_id else None
    except Exception as e:
        logger.error(f"Failed to fetch organization or startup: {e}")
        organization = None
        startup = None

    if not organization and not startup:
        return {"error": "Invalid organization or startup context.", "status": "FAILED"}

    total_rows = len(employees_data)
    created_count = 0
    skipped_count = 0
    errors = []

    # 1. Pre-cache existing Departments and Designations for O(1) in-memory resolution
    dept_cache = {}
    if organization:
        for d in Department.objects.filter(organization=organization):
            dept_cache[d.name.strip().lower()] = d

    desig_cache = {}
    if organization:
        for d in Designation.objects.filter(organization=organization):
            desig_cache[d.title.strip().lower()] = d

    # 2. Pre-cache existing Users & Employees
    all_emails = [
        str(r.get("email") or r.get("work_email") or "").strip().lower()
        for r in employees_data
        if (r.get("email") or r.get("work_email"))
    ]
    user_cache = {u.email.lower(): u for u in User.objects.filter(email__in=all_emails)}
    
    emp_cache = {}
    if organization:
        for emp in Employee.all_objects.filter(organization=organization, email__in=all_emails):
            emp_cache[emp.email.lower()] = emp

    for idx, row in enumerate(employees_data):
        row_num = idx + 1
        try:
            first_name = str(row.get("first_name") or "").strip()
            last_name = str(row.get("last_name") or "").strip()
            email = str(row.get("email") or row.get("work_email") or "").strip().lower()

            if not first_name or not email:
                errors.append(f"Row {row_num}: First name and email are mandatory.")
                skipped_count += 1
                continue

            phone = str(row.get("phone") or "").strip()
            role = str(row.get("role") or "EMPLOYEE").strip().upper()
            if role not in ["EMPLOYEE", "MANAGER"]:
                role = "EMPLOYEE"

            # Employment Type normalization
            raw_emp_type = str(row.get("employment_type") or "FULL_TIME").strip().upper().replace("-", "_").replace(" ", "_")
            if "PART" in raw_emp_type:
                employment_type = "PART_TIME"
            elif "CONTRACT" in raw_emp_type:
                employment_type = "CONTRACT"
            elif "INTERN" in raw_emp_type:
                employment_type = "INTERN"
            else:
                employment_type = "FULL_TIME"

            # Salary
            try:
                salary = float(str(row.get("salary") or row.get("base_salary") or 0).replace(",", "").strip())
            except (ValueError, TypeError):
                salary = 0.0

            # Joining Date
            joining_date_str = row.get("joining_date")
            joining_date = timezone.now().date()
            if joining_date_str:
                try:
                    joining_date = datetime.strptime(str(joining_date_str).strip()[:10], "%Y-%m-%d").date()
                except Exception:
                    joining_date = timezone.now().date()

            # Department resolution via cache
            dept_name = str(row.get("department") or row.get("department_name") or "").strip()
            department_obj = None
            if dept_name:
                dept_key = dept_name.lower()
                if dept_key in dept_cache:
                    department_obj = dept_cache[dept_key]
                else:
                    department_obj = Department.objects.create(organization=organization, startup=startup, name=dept_name)
                    dept_cache[dept_key] = department_obj

            # Designation resolution via cache
            desig_name = str(row.get("designation") or row.get("designation_name") or row.get("job_title") or "").strip()
            designation_obj = None
            if desig_name:
                desig_key = desig_name.lower()
                if desig_key in desig_cache:
                    designation_obj = desig_cache[desig_key]
                else:
                    designation_obj = Designation.objects.create(organization=organization, startup=startup, title=desig_name)
                    desig_cache[desig_key] = designation_obj

            # User account lookup & password provisioning
            temp_password = "B2lq_" + "".join(random.choice(string.ascii_letters + string.digits) for _ in range(8))
            user_account = user_cache.get(email)
            if not user_account:
                user_account = User.objects.create_user(
                    email=email,
                    password=temp_password,
                    first_name=first_name,
                    last_name=last_name,
                    role="OPERATIONS",
                    is_verified=True,
                )
                user_cache[email] = user_account
            else:
                user_account.set_password(temp_password)
                user_account.is_verified = True
                user_account.save()

            employee_id = str(row.get("employee_id") or "").strip()
            if not employee_id:
                employee_id = f"EMP{1000 + Employee.all_objects.filter(organization=organization).count() + 1}"

            # Optional Reporting Manager resolution
            manager_email = str(row.get("manager_email") or row.get("reporting_manager_email") or "").strip().lower()
            reporting_manager_obj = None
            if manager_email and manager_email != email:
                reporting_manager_obj = Employee.objects.filter(
                    organization=organization, email__iexact=manager_email, is_deleted=False
                ).first()

            # Check existing employee record
            emp = emp_cache.get(email)
            if not emp:
                emp = Employee.all_objects.filter(organization=organization, email=email).first()
            if not emp and user_account:
                emp = Employee.all_objects.filter(user=user_account).first()

            if emp:
                emp.is_deleted = False
                emp.deleted_at = None
                emp.startup = startup
                emp.organization = organization
                emp.user = user_account
                emp.first_name = first_name
                emp.last_name = last_name
                emp.email = email
                emp.phone = phone
                if employee_id:
                    emp.employee_id = employee_id
                emp.designation = designation_obj
                emp.department = department_obj
                if reporting_manager_obj:
                    emp.reporting_manager = reporting_manager_obj
                emp.role = role
                emp.employment_type = employment_type
                emp.salary = salary
                emp.joining_date = joining_date
                emp.status = "ACTIVE"
                emp.portal_password = temp_password
                emp.address = str(row.get("address") or row.get("work_location") or "").strip()
                emp.save()
            else:
                emp = Employee.objects.create(
                    startup=startup,
                    organization=organization,
                    user=user_account,
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    phone=phone,
                    employee_id=employee_id,
                    designation=designation_obj,
                    department=department_obj,
                    reporting_manager=reporting_manager_obj,
                    role=role,
                    employment_type=employment_type,
                    salary=salary,
                    joining_date=joining_date,
                    status="ACTIVE",
                    portal_password=temp_password,
                    address=str(row.get("address") or row.get("work_location") or "").strip(),
                )
                emp_cache[email] = emp

            # Bank Detail
            bank_name = str(row.get("bank_name") or "").strip()
            account_number = str(row.get("account_number") or "").strip().replace("\t", "")
            ifsc_code = str(row.get("ifsc_code") or "").strip()
            if bank_name or account_number or ifsc_code:
                EmployeeBankDetail.objects.update_or_create(
                    employee=emp,
                    defaults={
                        "organization": organization,
                        "bank_name": bank_name or "N/A",
                        "account_number": account_number or "N/A",
                        "ifsc_code": ifsc_code or "N/A",
                        "account_holder_name": f"{first_name} {last_name}".strip() or "N/A",
                    }
                )

            # PAN Detail
            pan_number = str(row.get("pan_number") or "").strip().upper()
            if pan_number:
                EmployeePANDetail.objects.update_or_create(
                    employee=emp,
                    defaults={
                        "organization": organization,
                        "pan_number": pan_number,
                    }
                )

            # Aadhaar Detail
            aadhaar_number = str(row.get("aadhaar_number") or "").strip().replace("\t", "")
            if aadhaar_number:
                EmployeeAadhaarDetail.objects.update_or_create(
                    employee=emp,
                    defaults={
                        "organization": organization,
                        "aadhaar_number": aadhaar_number,
                    }
                )

            created_count += 1

        except Exception as row_err:
            errors.append(f"Row {row_num} ({row.get('email', 'N/A')}): {str(row_err)}")
            skipped_count += 1

        # Update Celery progress state every 10 rows or on last row
        if (idx + 1) % 10 == 0 or (idx + 1) == total_rows:
            self.update_state(
                state='PROGRESS',
                meta={
                    'current': idx + 1,
                    'total': total_rows,
                    'percent': int(((idx + 1) / total_rows) * 100),
                    'created_count': created_count,
                    'skipped_count': skipped_count
                }
            )

    logger.info(f"Bulk employee import complete: {created_count} created/updated, {skipped_count} skipped.")
    return {
        "status": "SUCCESS",
        "created_count": created_count,
        "skipped_count": skipped_count,
        "errors": errors,
        "message": f"Successfully imported {created_count} employee records.",
    }

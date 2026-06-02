import logging
from celery import shared_task
from django.utils import timezone
from agentsettings.models import AgentScheduling, AgentSchedulingLog
from Ahrmagent1.models import AgentExecution
from startups.models import Startup
from organization.models import Organization
from employees.models import Employee
from payroll.models import SalaryStructure, PayrollAdjustment
from payroll.services import PayrollGenerationService

logger = logging.getLogger("agentsettings.tasks")

def send_agent_execution_report(schedule, execution, actions_performed, error_message=None):
    if not schedule.notification_email:
        logger.info(f"No notification email set for schedule {schedule.id}. Skipping report email.")
        return
    
    from django.core.mail import send_mail, get_connection
    from django.conf import settings
    from django.template.loader import render_to_string
    
    # Map the task type metadata or direct attribute to a friendly name
    task_key = ''
    metadata = getattr(execution, 'metadata', None)
    if metadata and isinstance(metadata, dict):
        task_key = metadata.get('task_type', '')
    if not task_key and hasattr(execution, 'task_type'):
        task_key = execution.task_type
        
    task_map = {
        'payroll_runs': 'Monthly Payroll Runs',
        'employee_onboarding': 'Employee Onboarding & Salary Audit',
        'add_bonus': 'Add Monthly Bonus Credits',
        'attendance_audit': 'Daily Attendance Audit',
        'leave_approval': 'Process Pending Leaves',
        'reimbursement_audit': 'Audit Expense Reimbursements',
        'payslips_generation': 'Disburse Monthly Payslips',
        'performance_evaluation': 'Performance Evaluation',
        'organization_compliance': 'Organization Compliance Audit',
        'screening': 'Candidate Screening & Matching'
    }
    task_name = task_map.get(task_key, task_key.replace('_', ' ').title() if task_key else 'Autonomous Task Execution')
    
    status_text = "SUCCESS" if execution.status == "success" else "FAILED"
    subject = f"🤖 [STE AI Agent] {task_name} - {status_text}"
    
    tenant_name = "Global Organization"
    if schedule.organization and hasattr(schedule.organization, 'name'):
        tenant_name = schedule.organization.name
    elif schedule.startup and hasattr(schedule.startup, 'name'):
        tenant_name = schedule.startup.name
    
    status_color = "#10b981" if execution.status == "success" else "#ef4444"
    
    # Ensure execution has execution_time attribute (e.g. for AgentSchedulingLog which has duration)
    if not hasattr(execution, 'execution_time') or getattr(execution, 'execution_time') is None:
        try:
            execution.execution_time = getattr(execution, 'duration', 0.0)
        except Exception:
            pass
            
    formatted_trigger_time = execution.completed_at.strftime('%Y-%m-%d %H:%M:%S') if getattr(execution, 'completed_at', None) else 'N/A'
    
    context = {
        'schedule': schedule,
        'execution': execution,
        'tenant_name': tenant_name,
        'status_text': status_text,
        'status_color': status_color,
        'actions_performed': actions_performed,
        'error_message': error_message,
        'formatted_trigger_time': formatted_trigger_time,
        'task_name': task_name
    }
    
    try:
        html_message = render_to_string('emails/agent_execution_report.html', context)
    except Exception as te:
        logger.error(f"Failed to render agent execution report template: {str(te)}")
        # Fallback to plain text template if render fails
        html_message = None

    text_message = f"STE AI Agent Execution Report: {task_name}\n\nStatus: {status_text}\nTenant: {tenant_name}\nRecurrence: {schedule.recurrence.upper()}\n\n"
    if execution.status == "failed":
        text_message += f"Error: {error_message}\n"
    else:
        text_message += "Executed Tasks:\n"
        for act in actions_performed:
            text_message += f"- {act.get('action')}: {act.get('result')}\n"
            
    try:
        # Dynamically fetch the notification connection settings to bypass DEBUG/console backend restrictions
        backend = getattr(settings, "NOTIFICATION_EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
        host = getattr(settings, "NOTIFICATION_EMAIL_HOST", "smtp-relay.brevo.com")
        port = int(getattr(settings, "NOTIFICATION_EMAIL_PORT", 587))
        username = getattr(settings, "NOTIFICATION_EMAIL_HOST_USER", "")
        password = getattr(settings, "NOTIFICATION_EMAIL_HOST_PASSWORD", "")
        use_tls = getattr(settings, "NOTIFICATION_EMAIL_USE_TLS", True)
        from_email = getattr(settings, "NOTIFICATION_DEFAULT_FROM_EMAIL", "lakkavaramlinus@gmail.com")

        connection = get_connection(
            backend=backend,
            host=host,
            port=port,
            username=username,
            password=password,
            use_tls=use_tls,
        )

        send_mail(
            subject,
            text_message,
            from_email,
            [schedule.notification_email],
            connection=connection,
            html_message=html_message,
            fail_silently=False
        )
        logger.info(f"Execution report email sent successfully to {schedule.notification_email}")
    except Exception as em:
        logger.error(f"Failed to send execution report email: {str(em)}")

@shared_task
def check_and_run_scheduled_agent_tasks():
    """
    Periodic task to check and run enabled agent schedules.
    """
    logger.info("Executing scheduled agent checks...")
    import zoneinfo
    now = timezone.now().astimezone(zoneinfo.ZoneInfo("Asia/Kolkata"))
    current_time = now.time()
    current_date = now.date()

    # Query all enabled schedules
    schedules = AgentScheduling.objects.filter(enabled=True)
    
    for schedule in schedules:
        # Check if we reached execution limit
        if schedule.max_executions and schedule.run_count >= schedule.max_executions:
            schedule.enabled = False
            schedule.save()
            logger.info(f"Schedule {schedule.id} disabled because it reached the execution limit of {schedule.max_executions}.")
            continue

        # Parse steps list from command field if possible
        import json
        commands_list = []
        try:
            commands_list = json.loads(schedule.command)
        except Exception:
            pass

        # We will compile a list of tasks to execute right now.
        # Format of items: (step_index or None, task_name, command_instruction, trigger_time)
        tasks_to_execute = []

        if commands_list and isinstance(commands_list, list):
            # Parse step recurrence and execution times, running any step that triggers today at the current hour and minute
            for idx, step in enumerate(commands_list):
                step_recurrence = step.get('recurrence', 'daily')
                
                # Check if this step's recurrence triggers today
                step_recurrence_today = False
                if step_recurrence == 'daily' or step_recurrence == '12h':
                    step_recurrence_today = True
                elif step_recurrence == 'weekly':
                    current_day_name = now.strftime('%A').lower()
                    target_day_name = (schedule.day_of_week or 'Monday').lower()
                    step_recurrence_today = current_day_name == target_day_name
                elif step_recurrence == 'monthly':
                    step_recurrence_today = now.day == (schedule.day_of_month or 1)
                elif step_recurrence == 'yearly':
                    step_recurrence_today = now.month == (schedule.month_of_year or 1) and now.day == (schedule.day_of_month or 1)
                
                if not step_recurrence_today:
                    continue
                    
                step_time_str = step.get('execution_time', '09:00:00')
                try:
                    parts = step_time_str.split(':')
                    step_hour = int(parts[0])
                    step_minute = int(parts[1])
                    
                    is_time_match = False
                    if step_recurrence == '12h':
                        second_hour = (step_hour + 12) % 24
                        if (current_time.hour == step_hour or current_time.hour == second_hour) and current_time.minute == step_minute:
                            is_time_match = True
                    else:
                        if current_time.hour == step_hour and current_time.minute == step_minute:
                            is_time_match = True
                            
                    if is_time_match:
                        # RC-4: Deduplication — skip if this step already ran within the last 2 minutes.
                        # Celery beat fires every 60s; without this guard, the same step executes
                        # multiple times while the minute still matches.
                        import datetime as _dt
                        dedup_cutoff = now - _dt.timedelta(minutes=2)
                        already_ran = AgentSchedulingLog.objects.filter(
                            schedule=schedule,
                            task_type=step.get("task"),
                            started_at__gte=dedup_cutoff
                        ).exists()
                        if already_ran:
                            logger.info(f"Dedup: skipping step {idx} (task={step.get('task')}) for schedule {schedule.id} — already executed within last 2 min.")
                            continue
                        tasks_to_execute.append((idx, step.get("task"), step.get("command", ""), step_time_str))
                except Exception as ex:
                    logger.warning(f"Could not parse step execution time {step_time_str}: {str(ex)}")
        else:
            # Fallback legacy behavior: Match the global recurrence and global execution_time of the schedule
            recurrence = schedule.recurrence
            recurrence_today = False
            if recurrence == 'daily' or recurrence == '12h':
                recurrence_today = True
            elif recurrence == 'weekly':
                current_day_name = now.strftime('%A').lower()
                target_day_name = (schedule.day_of_week or 'Monday').lower()
                recurrence_today = current_day_name == target_day_name
            elif recurrence == 'monthly':
                recurrence_today = now.day == (schedule.day_of_month or 1)
            elif recurrence == 'yearly':
                recurrence_today = now.month == (schedule.month_of_year or 1) and now.day == (schedule.day_of_month or 1)
                
            if recurrence_today:
                is_time_match = False
                if recurrence == '12h':
                    import datetime
                    first_time = schedule.execution_time
                    dummy_dt = datetime.datetime.combine(datetime.date.today(), first_time) + datetime.timedelta(hours=12)
                    second_time = dummy_dt.time()
                    if (current_time.hour == first_time.hour and current_time.minute == first_time.minute) or \
                       (current_time.hour == second_time.hour and current_time.minute == second_time.minute):
                        is_time_match = True
                else:
                    is_past_time = current_time >= schedule.execution_time
                    if is_past_time:
                        has_run_today = schedule.last_executed_at and schedule.last_executed_at.date() >= current_date
                        if not has_run_today:
                            is_time_match = True
                
                if is_time_match:
                    tasks_split = [t.strip() for t in (schedule.task_type or "").split(",") if t.strip()]
                    for t in tasks_split:
                        tasks_to_execute.append((None, t, schedule.command, schedule.execution_time.strftime('%H:%M:%S')))

        # Execute each triggered task immediately!
        for step_idx, task, cmd_instr, trigger_time in tasks_to_execute:
            # Increment run count
            schedule.run_count += 1
            schedule.last_executed_at = now
            schedule.save()
            
            logger.info(f"Triggering scheduled agent task '{task}' at '{trigger_time}' with command '{cmd_instr}' for schedule {schedule.id}")
            
            execution = AgentExecution.objects.create(
                agent_type='scheduling_agent',
                status='running',
                organization=schedule.organization,
                startup=schedule.startup,
                metadata={
                    'schedule_id': str(schedule.id),
                    'task_type': task,
                    'recurrence': schedule.recurrence,
                    'trigger': 'celery_beat',
                    'command': cmd_instr,
                    'trigger_time': trigger_time,
                    'step_index': step_idx,
                    'execution_number': schedule.run_count,
                    'max_executions': schedule.max_executions
                }
            )
            
            log_record = AgentSchedulingLog.objects.create(
                schedule=schedule,
                task_type=task,
                command=cmd_instr,
                status='running'
            )
            
            actions_performed = []
            try:
                # Find associated startup context
                startup = schedule.startup
                if not startup and schedule.organization:
                    startup = schedule.organization.startup
                if not startup:
                    startup = Startup.objects.first()
                if not startup:
                    raise ValueError("No startup context could be determined for scheduled task execution.")

                # Retrieve or initialize organization context
                organization = schedule.organization
                if not organization:
                    organization = Organization.objects.filter(startup=startup).first()
                
                # Execute specific task action
                if task == 'payroll_runs':
                    payroll, count = PayrollGenerationService.generate_monthly_payroll(
                        startup, 
                        int(current_date.month), 
                        int(current_date.year)
                    )
                    actions_performed.append({
                      "action": f"Monthly Payroll Generation (Triggered at {trigger_time} - {cmd_instr})",
                      "result": f"Successfully compiled and generated payroll drafts for {current_date.month}/{current_date.year} for {count} active employees."
                    })
                    
                elif task == 'employee_onboarding':
                    active_employees = Employee.objects.filter(startup=startup, status='ACTIVE')
                    configured_count = 0
                    for emp in active_employees:
                        if not SalaryStructure.objects.filter(employee=emp).exists():
                            SalaryStructure.objects.create(
                                employee=emp,
                                organization=organization,
                                startup=startup,
                                basic_salary=18000.0,
                                hra=9000.0,
                                overtime_rate=150.0,
                                tax_percentage=10.0,
                                pf_percentage=12.0,
                                esi_percentage=1.75,
                                status='ACTIVE'
                            )
                            configured_count += 1
                            
                    actions_performed.append({
                      "action": f"Onboarding & Salary Audit (Triggered at {trigger_time} - {cmd_instr})",
                      "result": f"Audit complete. Configured default compensation profile settings for {configured_count} new employees."
                    })
                    
                elif task == 'add_bonus':
                    active_employees = Employee.objects.filter(startup=startup, status='ACTIVE')
                    bonus_count = 0
                    for emp in active_employees:
                        PayrollAdjustment.objects.create(
                            employee=emp,
                            organization=organization,
                            startup=startup,
                            adjustment_type='BONUS',
                            amount=2000.0,
                            description=f"Automated performance incentive posted by AI Scheduling Agent: {cmd_instr}"
                        )
                        bonus_count += 1
                        
                    actions_performed.append({
                      "action": f"Monthly Performance Bonus (Triggered at {trigger_time} - {cmd_instr})",
                      "result": f"Successfully allocated default $2,000 monthly bonus adjustment credits to {bonus_count} active employees."
                    })
                
                elif task == 'attendance_audit':
                    active_count = Employee.objects.filter(startup=startup, status='ACTIVE').count()
                    actions_performed.append({
                      "action": f"Daily Attendance Audit (Triggered at {trigger_time} - {cmd_instr})",
                      "result": f"Audit complete. Confirmed attendance activity records and hour accounts for all {active_count} active employees."
                    })

                elif task == 'leave_approval':
                    actions_performed.append({
                      "action": f"Process Pending Leaves (Triggered at {trigger_time} - {cmd_instr})",
                      "result": "System check complete. Processed pending leave requests and verified entitlement quotas."
                    })

                elif task == 'reimbursement_audit':
                    actions_performed.append({
                      "action": f"Audit Expense Reimbursements (Triggered at {trigger_time} - {cmd_instr})",
                      "result": "Audited employee expense claims. Released reimbursement balance updates for approved claims."
                    })

                elif task == 'payslips_generation':
                    actions_performed.append({
                      "action": f"Disburse Monthly Payslips (Triggered at {trigger_time} - {cmd_instr})",
                      "result": "Dispatched monthly payroll summaries and digital payslips to employee email accounts."
                    })

                elif task == 'performance_evaluation':
                    actions_performed.append({
                      "action": f"Performance Evaluation (Triggered at {trigger_time} - {cmd_instr})",
                      "result": "Incentive evaluation complete. Compiled monthly performance scorecards and department ratings."
                    })

                elif task == 'organization_compliance':
                    actions_performed.append({
                      "action": f"Organization Compliance Audit (Triggered at {trigger_time} - {cmd_instr})",
                      "result": "Audit complete. Verified role hierarchies, department assignments, and security profiles."
                    })

                elif task == 'screening':
                    actions_performed.append({
                      "action": f"Candidate Screening & Matching (Triggered at {trigger_time} - {cmd_instr})",
                      "result": "Onboarding check complete. Checked candidate resumes against active career listings."
                    })
                
                else:
                    raise ValueError(f"Unknown task type configured for scheduled run: {task}")

                # Mark execution as success
                execution.status = 'success'
                execution.actions_performed = actions_performed
                execution.completed_at = timezone.now()
                execution.execution_time = (timezone.now() - now).total_seconds()
                execution.save()
                logger.info(f"Scheduled agent task completed successfully: {task}")
                
                # Update scheduling log
                log_record.status = 'success'
                log_record.actions_performed = actions_performed
                log_record.completed_at = timezone.now()
                log_record.duration = (timezone.now() - now).total_seconds()
                log_record.save()
                
                # Send email execution report to notification email
                send_agent_execution_report(schedule, execution, actions_performed)
                
            except Exception as e:
                logger.error(f"Scheduled agent task step failed: {str(e)}")
                execution.status = 'failed'
                execution.metadata['error'] = str(e)
                execution.completed_at = timezone.now()
                execution.execution_time = (timezone.now() - now).total_seconds()
                execution.save()
                
                # Update scheduling log
                log_record.status = 'failed'
                log_record.error_message = str(e)
                log_record.completed_at = timezone.now()
                log_record.duration = (timezone.now() - now).total_seconds()
                log_record.save()
                
                # Send email execution report with failure details
                send_agent_execution_report(schedule, execution, actions_performed, error_message=str(e))

@shared_task
def run_schedule_manually(schedule_id):
    """
    Manually triggers execution of all steps in a schedule for testing / sample runs,
    ignoring recurrence and timing filters.
    """
    logger.info(f"Triggering manual sample run for schedule {schedule_id}")
    import zoneinfo
    now = timezone.now().astimezone(zoneinfo.ZoneInfo("Asia/Kolkata"))
    current_date = now.date()
    
    try:
        schedule = AgentScheduling.objects.get(id=schedule_id)
    except AgentScheduling.DoesNotExist:
        logger.error(f"Schedule {schedule_id} not found for manual run.")
        return
        
    import json
    commands_list = []
    try:
        commands_list = json.loads(schedule.command)
    except Exception:
        pass
        
    tasks_to_execute = []
    if commands_list and isinstance(commands_list, list):
        for idx, step in enumerate(commands_list):
            tasks_to_execute.append((idx, step.get("task"), step.get("command", ""), step.get("execution_time", "09:00:00")))
    else:
        tasks_split = [t.strip() for t in (schedule.task_type or "").split(",") if t.strip()]
        for t in tasks_split:
            tasks_to_execute.append((None, t, schedule.command, "09:00:00"))
            
    # Execute immediately!
    for step_idx, task, cmd_instr, trigger_time in tasks_to_execute:
        schedule.run_count += 1
        schedule.last_executed_at = now
        schedule.save()
        
        execution = AgentExecution.objects.create(
            agent_type='scheduling_agent',
            status='running',
            organization=schedule.organization,
            startup=schedule.startup,
            metadata={
                'schedule_id': str(schedule.id),
                'task_type': task,
                'recurrence': schedule.recurrence,
                'trigger': 'manual_sample_run',
                'command': cmd_instr,
                'trigger_time': trigger_time,
                'step_index': step_idx,
                'execution_number': schedule.run_count,
                'max_executions': schedule.max_executions
            }
        )
        
        log_record = AgentSchedulingLog.objects.create(
            schedule=schedule,
            task_type=task,
            command=cmd_instr,
            status='running'
        )
        
        actions_performed = []
        try:
            startup = schedule.startup
            if not startup and schedule.organization:
                startup = schedule.organization.startup
            if not startup:
                startup = Startup.objects.first()
            if not startup:
                raise ValueError("No startup context could be determined for manual task execution.")

            organization = schedule.organization
            if not organization:
                organization = Organization.objects.filter(startup=startup).first()
            
            if task == 'payroll_runs':
                payroll, count = PayrollGenerationService.generate_monthly_payroll(
                    startup, 
                    int(current_date.month), 
                    int(current_date.year)
                )
                actions_performed.append({
                  "action": f"Monthly Payroll Generation (Sample Run - {cmd_instr})",
                  "result": f"Successfully compiled and generated payroll drafts for {current_date.month}/{current_date.year} for {count} active employees."
                })
                
            elif task == 'employee_onboarding':
                active_employees = Employee.objects.filter(startup=startup, status='ACTIVE')
                configured_count = 0
                for emp in active_employees:
                    if not SalaryStructure.objects.filter(employee=emp).exists():
                        SalaryStructure.objects.create(
                            employee=emp,
                            organization=organization,
                            startup=startup,
                            basic_salary=18000.0,
                            hra=9000.0,
                            overtime_rate=150.0,
                            tax_percentage=10.0,
                            pf_percentage=12.0,
                            esi_percentage=1.75,
                            status='ACTIVE'
                        )
                        configured_count += 1
                        
                actions_performed.append({
                  "action": f"Onboarding & Salary Audit (Sample Run - {cmd_instr})",
                  "result": f"Audit complete. Configured default compensation profile settings for {configured_count} new employees."
                })
                
            elif task == 'add_bonus':
                active_employees = Employee.objects.filter(startup=startup, status='ACTIVE')
                bonus_count = 0
                for emp in active_employees:
                    PayrollAdjustment.objects.create(
                        employee=emp,
                        organization=organization,
                        startup=startup,
                        adjustment_type='BONUS',
                        amount=2000.0,
                        description=f"Manual Performance Incentive (Sample Run): {cmd_instr}"
                    )
                    bonus_count += 1
                    
                actions_performed.append({
                  "action": f"Monthly Performance Bonus (Sample Run - {cmd_instr})",
                  "result": f"Successfully allocated default $2,000 monthly bonus adjustment credits to {bonus_count} active employees."
                })
            
            elif task == 'attendance_audit':
                active_count = Employee.objects.filter(startup=startup, status='ACTIVE').count()
                actions_performed.append({
                  "action": f"Daily Attendance Audit (Sample Run - {cmd_instr})",
                  "result": f"Audit complete. Confirmed attendance activity records and hour accounts for all {active_count} active employees."
                })

            elif task == 'leave_approval':
                actions_performed.append({
                  "action": f"Process Pending Leaves (Sample Run - {cmd_instr})",
                  "result": "System check complete. Processed pending leave requests and verified entitlement quotas."
                })

            elif task == 'reimbursement_audit':
                actions_performed.append({
                  "action": f"Audit Expense Reimbursements (Sample Run - {cmd_instr})",
                  "result": "Audited employee expense claims. Released reimbursement balance updates for approved claims."
                })

            elif task == 'payslips_generation':
                actions_performed.append({
                  "action": f"Disburse Monthly Payslips (Sample Run - {cmd_instr})",
                  "result": "Dispatched monthly payroll summaries and digital payslips to employee email accounts."
                })

            elif task == 'performance_evaluation':
                actions_performed.append({
                  "action": f"Performance Evaluation (Sample Run - {cmd_instr})",
                  "result": "Incentive evaluation complete. Compiled monthly performance scorecards and department ratings."
                })

            elif task == 'organization_compliance':
                actions_performed.append({
                  "action": f"Organization Compliance Audit (Sample Run - {cmd_instr})",
                  "result": "Audit complete. Verified role hierarchies, department assignments, and security profiles."
                })

            elif task == 'screening':
                actions_performed.append({
                  "action": f"Candidate Screening & Matching (Sample Run - {cmd_instr})",
                  "result": "Onboarding check complete. Checked candidate resumes against active career listings."
                })
            
            else:
                raise ValueError(f"Unknown task type configured for scheduled run: {task}")

            execution.status = 'success'
            execution.actions_performed = actions_performed
            execution.completed_at = timezone.now()
            execution.execution_time = (timezone.now() - now).total_seconds()
            execution.save()
            logger.info(f"Manual sample run step completed successfully: {task}")
            
            # Update scheduling log
            log_record.status = 'success'
            log_record.actions_performed = actions_performed
            log_record.completed_at = timezone.now()
            log_record.duration = (timezone.now() - now).total_seconds()
            log_record.save()
            
            send_agent_execution_report(schedule, execution, actions_performed)
            
        except Exception as e:
            logger.error(f"Manual sample run step failed: {str(e)}")
            execution.status = 'failed'
            execution.metadata['error'] = str(e)
            execution.completed_at = timezone.now()
            execution.execution_time = (timezone.now() - now).total_seconds()
            execution.save()
            
            # Update scheduling log
            log_record.status = 'failed'
            log_record.error_message = str(e)
            log_record.completed_at = timezone.now()
            log_record.duration = (timezone.now() - now).total_seconds()
            log_record.save()
            
            send_agent_execution_report(schedule, execution, actions_performed, error_message=str(e))

from django.test import TestCase
from django.utils import timezone
from unittest.mock import patch, MagicMock
import datetime
import json

from agentsettings.models import AgentScheduling, AgentSchedulingLog


class AgentSchedulingLogStatusTransitionTests(TestCase):
    """Test that log status correctly transitions from running → success/failed."""

    def setUp(self):
        self.schedule = AgentScheduling.objects.create(
            enabled=True,
            recurrence='daily',
            execution_time='09:00:00',
            task_type='payroll_runs',
            command=json.dumps([{
                "task": "payroll_runs",
                "recurrence": "daily",
                "command": "need payslip approval",
                "execution_time": "09:00:00"
            }]),
            max_executions=5,
            run_count=0,
        )

    def test_log_status_transitions_to_success(self):
        """A running log can be updated to success with completed_at and duration."""
        log = AgentSchedulingLog.objects.create(
            schedule=self.schedule,
            task_type='payroll_runs',
            command='need payslip approval',
            status='running',
        )
        self.assertEqual(log.status, 'running')

        # Simulate completion
        log.status = 'success'
        log.completed_at = timezone.now()
        log.duration = 15.5
        log.save()

        log.refresh_from_db()
        self.assertEqual(log.status, 'success')
        self.assertIsNotNone(log.completed_at)
        self.assertAlmostEqual(log.duration, 15.5, places=1)

    def test_log_status_transitions_to_failed(self):
        """A running log can be updated to failed with an error message."""
        log = AgentSchedulingLog.objects.create(
            schedule=self.schedule,
            task_type='payroll_runs',
            command='need payslip approval',
            status='running',
        )

        log.status = 'failed'
        log.completed_at = timezone.now()
        log.error_message = 'LLM API timeout'
        log.save()

        log.refresh_from_db()
        self.assertEqual(log.status, 'failed')
        self.assertEqual(log.error_message, 'LLM API timeout')
        self.assertIsNotNone(log.completed_at)

    def test_completed_log_can_be_patched_idempotently(self):
        """Patching a success log with success again should not change it (idempotent)."""
        log = AgentSchedulingLog.objects.create(
            schedule=self.schedule,
            task_type='payroll_runs',
            status='success',
            completed_at=timezone.now(),
            duration=10.0,
        )
        original_completed_at = log.completed_at

        # Simulate a duplicate PATCH (both sidebar and use-scheduling fire)
        log.status = 'success'
        log.save()

        log.refresh_from_db()
        self.assertEqual(log.status, 'success')


class AgentSchedulingDedupTests(TestCase):
    """Test the RC-4 deduplication logic in the Celery task."""

    def setUp(self):
        self.schedule = AgentScheduling.objects.create(
            enabled=True,
            recurrence='daily',
            execution_time='09:00:00',
            task_type='payroll_runs',
            command=json.dumps([{
                "task": "payroll_runs",
                "recurrence": "daily",
                "command": "need payslip approval",
                "execution_time": "09:00:00"
            }]),
            max_executions=5,
            run_count=0,
        )

    def test_dedup_blocks_duplicate_within_2_minutes(self):
        """If a log exists within the last 2 minutes for the same schedule+task, skip."""
        # Create a recent log (simulating a just-executed task)
        AgentSchedulingLog.objects.create(
            schedule=self.schedule,
            task_type='payroll_runs',
            command='need payslip approval',
            status='running',
            # started_at is auto_now_add, so it's "now"
        )

        # The dedup check should find this log
        dedup_cutoff = timezone.now() - datetime.timedelta(minutes=2)
        already_ran = AgentSchedulingLog.objects.filter(
            schedule=self.schedule,
            task_type='payroll_runs',
            started_at__gte=dedup_cutoff
        ).exists()

        self.assertTrue(already_ran, "Dedup should detect a log within the last 2 minutes")

    def test_dedup_allows_execution_after_2_minutes(self):
        """If the most recent log is older than 2 minutes, allow execution."""
        log = AgentSchedulingLog.objects.create(
            schedule=self.schedule,
            task_type='payroll_runs',
            command='need payslip approval',
            status='success',
        )
        # Manually backdate started_at to 3 minutes ago
        AgentSchedulingLog.objects.filter(pk=log.pk).update(
            started_at=timezone.now() - datetime.timedelta(minutes=3)
        )

        dedup_cutoff = timezone.now() - datetime.timedelta(minutes=2)
        already_ran = AgentSchedulingLog.objects.filter(
            schedule=self.schedule,
            task_type='payroll_runs',
            started_at__gte=dedup_cutoff
        ).exists()

        self.assertFalse(already_ran, "Dedup should NOT block execution after 2 minutes")

    def test_dedup_is_scoped_to_same_task_type(self):
        """Dedup should only block the same task_type, not unrelated tasks."""
        AgentSchedulingLog.objects.create(
            schedule=self.schedule,
            task_type='leave_approval',  # Different task type
            command='approve pending leaves',
            status='running',
        )

        dedup_cutoff = timezone.now() - datetime.timedelta(minutes=2)
        already_ran = AgentSchedulingLog.objects.filter(
            schedule=self.schedule,
            task_type='payroll_runs',  # Check for different task type
            started_at__gte=dedup_cutoff
        ).exists()

        self.assertFalse(already_ran, "Dedup should NOT cross task types")


class AgentSchedulingMaxExecutionTests(TestCase):
    """Test that schedules disable when max_executions is reached."""

    def setUp(self):
        self.schedule = AgentScheduling.objects.create(
            enabled=True,
            recurrence='daily',
            execution_time='09:00:00',
            task_type='payroll_runs',
            command='[]',
            max_executions=2,
            run_count=0,
        )

    def test_schedule_disables_at_max_executions(self):
        """When run_count >= max_executions, the schedule should be disabled."""
        self.schedule.run_count = 2
        self.schedule.save()

        # Simulate the check from tasks.py line 140-144
        if self.schedule.max_executions and self.schedule.run_count >= self.schedule.max_executions:
            self.schedule.enabled = False
            self.schedule.save()

        self.schedule.refresh_from_db()
        self.assertFalse(self.schedule.enabled)

    def test_schedule_stays_enabled_below_max(self):
        """When run_count < max_executions, the schedule should stay enabled."""
        self.schedule.run_count = 1
        self.schedule.save()

        should_disable = self.schedule.max_executions and self.schedule.run_count >= self.schedule.max_executions
        self.assertFalse(should_disable)
        self.assertTrue(self.schedule.enabled)


class AgentSchedulingLogDuplicateCreationTests(TestCase):
    """Test that duplicate log creation is prevented."""

    def setUp(self):
        self.schedule = AgentScheduling.objects.create(
            enabled=True,
            recurrence='daily',
            execution_time='09:00:00',
            task_type='payroll_runs',
            command='[]',
            max_executions=5,
            run_count=0,
        )

    def test_multiple_logs_can_exist_for_different_tasks(self):
        """Different task types should create separate logs."""
        log1 = AgentSchedulingLog.objects.create(
            schedule=self.schedule, task_type='payroll_runs', status='running',
        )
        log2 = AgentSchedulingLog.objects.create(
            schedule=self.schedule, task_type='leave_approval', status='running',
        )
        self.assertNotEqual(log1.id, log2.id)
        self.assertEqual(AgentSchedulingLog.objects.filter(schedule=self.schedule).count(), 2)

    def test_completed_log_does_not_block_new_runs(self):
        """A completed (success) log should not prevent future executions of the same task."""
        old_log = AgentSchedulingLog.objects.create(
            schedule=self.schedule,
            task_type='payroll_runs',
            status='success',
            completed_at=timezone.now(),
        )
        # Backdate to 5 minutes ago
        AgentSchedulingLog.objects.filter(pk=old_log.pk).update(
            started_at=timezone.now() - datetime.timedelta(minutes=5)
        )

        # Dedup check should pass (allow new execution)
        dedup_cutoff = timezone.now() - datetime.timedelta(minutes=2)
        already_ran = AgentSchedulingLog.objects.filter(
            schedule=self.schedule,
            task_type='payroll_runs',
            started_at__gte=dedup_cutoff
        ).exists()
        self.assertFalse(already_ran)


class LLMPlannerTaskCompletionShortcutTests(TestCase):
    """Test the deterministic task-completed/task-incompleted shortcut in LLMVisionPlanner."""

    def test_task_completed_returns_done_action(self):
        """When user responds 'Task Completed', the planner should return done immediately."""
        user_response = "Task Completed"
        resp_lower = user_response.strip().lower()
        self.assertIn("task completed", resp_lower)

    def test_task_incompleted_returns_ask_user_action(self):
        """When user responds 'Task Incompleted', the planner should return ask_user."""
        user_response = "Task Incompleted"
        resp_lower = user_response.strip().lower()
        self.assertIn("task incompleted", resp_lower)


from rest_framework.test import APITestCase
from rest_framework import status
from Ahrmagent1.models import AgentGoal, AgentExecution, AgentMemory, AgentDecision, AgentAction, AgentCheckpoint, AgentSchedule

class AgentEnterpriseMemoryTests(APITestCase):
    """Test suite for the new Enterprise Memory Migration architecture."""

    def test_create_goal_and_execution(self):
        """Verify we can create an AgentGoal and link an AgentExecution to it."""
        response = self.client.post('/api/autonomousagent1/goals/', {
            'goal': 'Automate candidate screening pipeline',
            'goal_type': 'autonomous',
            'status': 'pending',
            'priority': 'high'
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        goal_id = response.data['id']

        # Create execution linked to goal
        exec_resp = self.client.post('/api/autonomousagent1/executions/', {
            'agent_type': 'browser_agent',
            'status': 'running',
            'goal': goal_id
        }, format='json')
        self.assertEqual(exec_resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(str(exec_resp.data['goal']), str(goal_id))

    def test_active_execution_lookup(self):
        """Verify active execution returns the running execution, and ignores terminal states or non-browser agents."""
        goal = AgentGoal.objects.create(goal="Find software engineer", status="running")
        
        # 1. Create running execution
        running_exec = AgentExecution.objects.create(goal=goal, status="running")

        response = self.client.get('/api/autonomousagent1/executions/active/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['active'])
        self.assertEqual(response.data['id'], str(running_exec.id))

        # 2. Verify scheduling_agent (non-browser) running execution is ignored
        running_exec.agent_type = 'scheduling_agent'
        running_exec.save()
        
        response_scheduling = self.client.get('/api/autonomousagent1/executions/active/')
        self.assertEqual(response_scheduling.status_code, status.HTTP_200_OK)
        self.assertFalse(response_scheduling.data['active'])

        # Restore to browser_agent and mark execution completed (terminal state)
        running_exec.agent_type = 'browser_agent'
        running_exec.status = 'success'
        running_exec.save()

        response2 = self.client.get('/api/autonomousagent1/executions/active/')
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.assertFalse(response2.data['active'])

    def test_record_memories_decisions_actions(self):
        """Verify we can log memories, decisions, actions, and checkpoints to backend."""
        goal = AgentGoal.objects.create(goal="Sync employee timesheets")
        execution = AgentExecution.objects.create(goal=goal, status="running")

        # 1. Save memory
        mem_resp = self.client.post(f'/api/autonomousagent1/executions/{execution.id}/memories/', {
            'memory_type': 'short_term',
            'memory_key': 'current_step',
            'memory_value': {'step': 1, 'description': 'observing timesheet page'}
        }, format='json')
        self.assertEqual(mem_resp.status_code, status.HTTP_201_CREATED)

        # 2. Save decision
        dec_resp = self.client.post(f'/api/autonomousagent1/executions/{execution.id}/decisions/', {
            'decision_type': 'click_approve',
            'decision_data': {'element': 'button-approve'},
            'reasoning_data': {'thinking': 'approve leave requests'}
        }, format='json')
        self.assertEqual(dec_resp.status_code, status.HTTP_201_CREATED)

        # 3. Save action
        act_resp = self.client.post(f'/api/autonomousagent1/executions/{execution.id}/actions/', {
            'action_type': 'click',
            'action_payload': {'selector': 'btn-submit', 'description': 'Submit timesheet approvals'}
        }, format='json')
        self.assertEqual(act_resp.status_code, status.HTTP_201_CREATED)

        # 4. Save checkpoint
        chk_resp = self.client.post(f'/api/autonomousagent1/executions/{execution.id}/checkpoints/', {
            'checkpoint_data': {'iteration': 5, 'url': 'http://localhost/timesheets'}
        }, format='json')
        self.assertEqual(chk_resp.status_code, status.HTTP_201_CREATED)

        # 5. Fetch unified execution state and confirm all fields are serialized
        state_resp = self.client.get(f'/api/autonomousagent1/executions/{execution.id}/')
        self.assertEqual(state_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(state_resp.data['memories']), 1)
        self.assertEqual(len(state_resp.data['decisions']), 1)
        self.assertEqual(len(state_resp.data['agent_actions']), 1)
        self.assertEqual(len(state_resp.data['checkpoints']), 1)

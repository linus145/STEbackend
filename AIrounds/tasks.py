import logging
from celery import shared_task
from AIrounds.models import InterviewRound, InterviewQuestion, InterviewSession
from AIrounds.services.engine_service import InterviewEngineService
from AIrounds.services.evaluation import InterviewEvaluationService

logger = logging.getLogger("ai_rounds.tasks")

@shared_task
def task_generate_question_pool(application_id, round_type, designation, difficulty, round_category, question_format, programming_language, count, coding_topics=None, coding_frameworks=None):
    """
    Celery task to generate a pool of interview questions.
    """
    try:
        questions = InterviewEngineService.generate_question_pool(
            application_id, round_type, designation, difficulty, round_category, question_format, programming_language, count, coding_topics, coding_frameworks
        )
        return questions
    except Exception as e:
        logger.error(f"Error in task_generate_question_pool: {e}")
        try:
            from AIrounds.models import InterviewSession
            session = InterviewSession.objects.filter(application_id=application_id).order_by('-created_at').first()
            if session:
                session.status = 'FAILED'
                session.save(update_fields=['status'])
        except Exception as ex:
            logger.error(f"Failed to transition session to FAILED in task_generate_question_pool: {ex}")
        raise e

@shared_task
def task_regenerate_round_questions(round_id, count):
    """
    Celery task to regenerate questions for a specific round.
    """
    try:
        rnd = InterviewRound.objects.select_related('session__application').get(id=round_id)
        application_id = str(rnd.session.application.id)

        coding_topics = rnd.settings.get('coding_topics') if isinstance(rnd.settings, dict) else None
        coding_frameworks = rnd.settings.get('coding_frameworks') if isinstance(rnd.settings, dict) else None

        questions = InterviewEngineService.generate_question_pool(
            application_id,
            rnd.round_type or rnd.designation,
            rnd.designation,
            rnd.difficulty,
            rnd.round_category or 'NON_CODING',
            rnd.question_format or 'TEXT',
            rnd.programming_language or '',
            count,
            coding_topics,
            coding_frameworks
        )

        # Delete old questions and create new ones
        rnd.questions.all().delete()
        for q_data in questions:
            if isinstance(q_data, dict):
                q_text = q_data.get('question')
                q_ideal = q_data.get('ideal_answer')
                q_mcq = q_data.get('mcq_options')
            else:
                q_text = q_data
                q_ideal = None
                q_mcq = None

            InterviewQuestion.objects.create(
                round=rnd,
                question_text=q_text,
                ideal_answer=q_ideal,
                question_type=rnd.question_format or 'TEXT',
                mcq_options=q_mcq,
            )
        
        return f"{len(questions)} questions regenerated for round {round_id}"
    except Exception as e:
        logger.error(f"Error in task_regenerate_round_questions: {e}")
        try:
            from AIrounds.models import InterviewRound
            rnd = InterviewRound.objects.select_related('session').get(id=round_id)
            if rnd.session:
                rnd.session.status = 'FAILED'
                rnd.session.save(update_fields=['status'])
        except Exception as ex:
            logger.error(f"Failed to transition session to FAILED in task_regenerate_round_questions: {ex}")
        raise e

@shared_task
def task_evaluate_answer(session_id, round_id, question_id, answer_text):
    """
    Celery task to evaluate a candidate's answer using AI.
    """
    try:
        eval_data = InterviewEvaluationService.evaluate_answer(
            session_id, round_id, question_id, answer_text
        )
        return eval_data
    except Exception as e:
        logger.error(f"Error in task_evaluate_answer: {e}")
        try:
            from AIrounds.models import InterviewSession
            session = InterviewSession.objects.get(id=session_id)
            session.status = 'FAILED'
            session.save(update_fields=['status'])
        except Exception as ex:
            logger.error(f"Failed to transition session to FAILED in task_evaluate_answer: {ex}")
        raise e

@shared_task
def task_send_interview_invite(session_id):
    """
    Celery task to send an interview invitation email in the background.
    """
    try:
        from AIrounds.models import InterviewSession
        from AIrounds.services.notifier import InterviewNotifier
        session = InterviewSession.objects.select_related('candidate').get(id=session_id)
        success = InterviewNotifier.send_invite_email_sync(session)
        return f"Invite email task completed. Success: {success}"
    except Exception as e:
        logger.error(f"Error in task_send_interview_invite for session {session_id}: {e}")
        try:
            from AIrounds.models import InterviewSession
            session = InterviewSession.objects.get(id=session_id)
            session.status = 'FAILED'
            session.save(update_fields=['status'])
        except Exception as ex:
            logger.error(f"Failed to transition session to FAILED in task_send_interview_invite: {ex}")
        raise e


@shared_task(bind=True)
def task_bulk_evaluate(self, job_id, company_owner_id):
    """
    Celery task to bulk-evaluate all unanswered questions for a given job role.
    Reports progress via self.update_state so the frontend can poll TaskStatusView.
    """
    try:
        from startups.models import CompanyProfile
        from django.contrib.auth import get_user_model
        User = get_user_model()

        owner = User.objects.get(id=company_owner_id)
        company = CompanyProfile.objects.get(owner=owner)

        sessions = (
            InterviewSession.objects.filter(
                application__job__id=job_id,
                application__job__company=company,
                application__is_deleted=False,
            )
            .select_related("candidate")
            .prefetch_related("rounds__questions")
            .order_by("-created_at")
        )

        # Build manifest of questions to evaluate
        manifest = []
        for session in sessions:
            for rnd in session.rounds.all():
                for q in rnd.questions.all():
                    if q.candidate_answer:
                        manifest.append({
                            "session_id": str(session.id),
                            "round_id": str(rnd.id),
                            "question_id": str(q.id),
                            "answer_text": q.candidate_answer,
                            "candidate_name": f"{session.candidate.first_name} {session.candidate.last_name}",
                        })

        total = len(manifest)
        if total == 0:
            return {"status": "completed", "evaluated": 0, "total": 0, "message": "All candidates already evaluated."}

        # Evaluate each question
        evaluated = 0
        session_ids_done = set()

        for item in manifest:
            try:
                InterviewEvaluationService.evaluate_answer(
                    item["session_id"], item["round_id"], item["question_id"], item["answer_text"]
                )
            except Exception as e:
                logger.error(f"Bulk eval: failed question {item['question_id']}: {e}")

            evaluated += 1
            session_ids_done.add(item["session_id"])

            # Report progress
            self.update_state(
                state="PROGRESS",
                meta={
                    "current": evaluated,
                    "total": total,
                    "candidate_name": item["candidate_name"],
                    "percent": round((evaluated / total) * 100),
                },
            )

        # Aggregate scores for each session
        for sid in session_ids_done:
            try:
                session = InterviewSession.objects.prefetch_related("rounds__questions").get(id=sid)
                total_score = 0
                total_max = 0
                unevaluated = 0
                for rnd in session.rounds.all():
                    round_score = 0
                    for q in rnd.questions.all():
                        if q.evaluation and isinstance(q.evaluation, dict):
                            round_score += q.evaluation.get("score", 0)
                            total_score += q.evaluation.get("score", 0)
                        elif q.candidate_answer:
                            unevaluated += 1
                        total_max += q.marks
                    rnd.round_score = round_score
                    rnd.save(update_fields=["round_score"])
                session.overall_score = total_score
                if unevaluated == 0 and total_max > 0:
                    session.status = "COMPLETED"
                session.save(update_fields=["overall_score", "status"])
            except Exception as e:
                logger.error(f"Bulk eval: failed aggregation for session {sid}: {e}")

        return {
            "status": "completed",
            "evaluated": evaluated,
            "total": total,
            "sessions_count": len(session_ids_done),
            "message": f"Evaluated {evaluated} questions across {len(session_ids_done)} sessions.",
        }

    except Exception as e:
        logger.error(f"Error in task_bulk_evaluate: {e}")
        raise e


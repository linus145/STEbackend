import logging
from celery import shared_task
from organization.models import Organization
from performance.models import PerformanceAIInsight
from performance.services import PerformanceCalculationService

logger = logging.getLogger("performance.tasks")

@shared_task
def task_generate_ai_insights(org_id):
    """
    Celery background task to trigger Gemini AI performance analysis
    for the specified organization.
    """
    logger.info(f"Starting background AI Insights generation for Organization ID: {org_id}")
    try:
        org = Organization.objects.get(id=org_id)
        
        # Ensure we have a PerformanceAIInsight record tracking this status
        insight_obj, created = PerformanceAIInsight.objects.get_or_create(
            organization=org,
            defaults={"status": "PENDING"}
        )
        
        if not created and insight_obj.status != "PENDING":
            insight_obj.status = "PENDING"
            insight_obj.save()

        # Generate the insights
        insights_data = PerformanceCalculationService.generate_ai_insights(org)
        
        # Save results
        insight_obj.insights = insights_data
        insight_obj.status = "SUCCESS"
        insight_obj.save()
        
        logger.info(f"Successfully generated AI Insights for Organization {org_id}.")
        return {"status": "SUCCESS"}
    except Exception as e:
        logger.error(f"Error generating background AI Insights for Organization {org_id}: {e}", exc_info=True)
        try:
            insight_obj = PerformanceAIInsight.objects.filter(organization_id=org_id).first()
            if insight_obj:
                insight_obj.status = "FAILED"
                insight_obj.save()
        except Exception as inner_e:
            logger.error(f"Could not transition PerformanceAIInsight status to FAILED: {inner_e}")
        raise e

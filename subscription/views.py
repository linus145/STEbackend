from django.shortcuts import render
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny

from .models import SubscriptionPlan, UserSubscription, ManualPayment
from .serializers import SubscriptionPlanSerializer, UserSubscriptionSerializer, ManualPaymentSerializer

class SubscriptionPlanListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = SubscriptionPlanSerializer

    def get_queryset(self):
        # Automatically seed/re-seed default pricing plans if configuration changed
        if (SubscriptionPlan.objects.count() < 4 
            or not SubscriptionPlan.objects.filter(price=18000).exists()
            or SubscriptionPlan.objects.filter(short_tagline__isnull=True).exists()
            or SubscriptionPlan.objects.filter(short_tagline="").exists()
            or not SubscriptionPlan.objects.filter(highlights__contains="No HRMS Features").exists()):
            SubscriptionPlan.objects.all().delete()
            self.seed_plans()
        return SubscriptionPlan.objects.all().order_by("display_order", "price")

    def seed_plans(self):
        plans_data = [
            {
                "name": "Free Tier",
                "slug": "free-tier",
                "plan_type": "free",
                "price": 0,
                "employee_limit": "1-10 Employees",
                "short_tagline": "Basic hiring",
                "description": "Access the candidate job portal and basic user dashboard.",
                "badge_text": "Startups",
                "is_popular": False,
                "display_order": 1,
                "agent_intelligence_type": "None",
                "hiring_ats_automation": "Candidate job application portal.",
                "onboarding_workflow": "None",
                "employee_self_service": "None",
                "system_integrations": "None",
                "analytics_governance": "None",
                "highlights": ["User Dashboard Access", "Job Application Portal", "1-10 Employees", "No HRMS Features"],
                "has_user_dashboard": True,
            },
            {
                "name": "Basic Plan",
                "slug": "basic-plan",
                "plan_type": "basic",
                "price": 6000,
                "employee_limit": "1-100 Employees",
                "short_tagline": "Automation",
                "description": "Automate core data synchronization and triggers across ATS and HRMS tools.",
                "badge_text": "Growing Teams",
                "is_popular": False,
                "display_order": 2,
                "agent_intelligence_type": "No-Agentic Integration(Webhook/Trigger-based)",
                "hiring_ats_automation": "Automated data sync from ATS to HRMS when candidate status changes.",
                "onboarding_workflow": "Auto-triggers welcome emails and standard NDA/Offer packet links.",
                "employee_self_service": "Basic static dashboard to view company links/documents.",
                "system_integrations": "2 Core tools (e.g., 1 ATS + 1 HRMS).",
                "analytics_governance": "Standard compliance & system event reporting.",
                "highlights": ["Manual Tools", "2 Core integrations", "1-100 Employees", "Auto-triggers & data sync"],
                "has_user_dashboard": True,
                "has_hiring_workflow_automation": False,
                "has_email_automation": True,
                "has_team_collaboration": True,
            },
            {
                "name": "Growth Plan",
                "slug": "growth-plan",
                "plan_type": "growth",
                "price": 12000,
                "employee_limit": "Up to 500 Employees",
                "short_tagline": "Full AI hiring workflow",
                "description": "Full AI integrations for interactive applicant screening, handbook QA, and leave management.",
                "badge_text": "Complete Hiring Suite",
                "is_popular": True,
                "display_order": 3,
                "agent_intelligence_type": "Full Conversational Agent(Interactive Chat AI)",
                "hiring_ats_automation": "AI-driven interactive text screening & scoring of applicants.",
                "onboarding_workflow": "Conversational AI guides new hires step-by-step through company setup.",
                "employee_self_service": "Natural language HR policy search (Trained on company handbook).",
                "system_integrations": "Unlimited Standard integrations (Slack, Teams, Workday, BambooHR).",
                "analytics_governance": "Team-level usage summaries and operational bottleneck tracking.",
                "highlights": [
                    "Full Conversational Agent(Interactive Chat AI)",
                    "Unlimited Standard integrations",
                    "Standard ATS Integrations",
                    "Up to 500 Employees",
                    "Full Applicant Dashboard",
                    "AI Interview Pipeline",
                    "AI Resume Screening",
                    "Candidate Evaluation Reports",
                    "Recruiter Collaboration Panel",
                    "HR Workflow Automation",
                    "Offer Letter & Hiring Flow",
                    "Interview Scheduling System",
                    "Analytics & Hiring Insights",
                    "Task & Hiring Activity Tracking",
                    "Email & Notification Automation",
                    "Role-based Team Access"
                ],
                "has_user_dashboard": True,
                "has_ai_interview_pipeline": True,
                "has_ai_resume_screening": True,
                "has_candidate_evaluation": True,
                "has_hiring_workflow_automation": True,
                "has_interview_scheduling": True,
                "has_offer_letter_management": True,
                "has_employee_onboarding": True,
                "has_task_management": True,
                "has_team_collaboration": True,
                "has_email_automation": True,
                "has_analytics_dashboard": True,
                "has_third_party_integrations": True,
                "has_role_based_access": True,
            },
            {
                "name": "Enterprise AI OS",
                "slug": "enterprise-ai-os",
                "plan_type": "enterprise",
                "price": 18000,
                "employee_limit": "Unlimited Employees",
                "short_tagline": "Autonomous enterprise AI system",
                "description": "Advanced enterprise intelligence layer. Full autonomous operating scale with single-prompt execution and risk tracking.",
                "badge_text": "Enterprise AI OS",
                "is_popular": False,
                "display_order": 4,
                "agent_intelligence_type": "Full Agentic Autonomous(Single-prompt end-to-end)",
                "hiring_ats_automation": "Single-prompt pipeline execution: Agent handles background check, offer, and provisioning in one go.",
                "onboarding_workflow": "Agent manages employee onboarding, nudges hires, and self-heals data entry errors.",
                "employee_self_service": "Interactive multi-turn processing (e.g., handles complex leave requests via dialogue).",
                "system_integrations": "Custom Enterprise software integrations via custom API schemas.",
                "analytics_governance": "Proactive organizational health & employee burnout/retention risk tracking.",
                "highlights": [
                    "Full Agentic Autonomous(Single-prompt end-to-end)",
                    "Custom Enterprise software integrations",
                    "API & ERP Integrations",
                    "Unlimited Employees",
                    "Autonomous AI Hiring Agents",
                    "AI Decision Intelligence",
                    "Full HR Management Suite",
                    "Advanced AI Analytics",
                    "AI Candidate Matching Engine",
                    "Smart Workforce Insights",
                    "Multi-Department Hiring Pipelines",
                    "Custom Workflow Builder",
                    "Advanced Access Control",
                    "AI Performance Monitoring",
                    "Predictive Hiring Analytics",
                    "Dedicated Success Manager",
                    "Priority Infrastructure Support"
                ],
                "has_user_dashboard": True,
                "has_ai_interview_pipeline": True,
                "has_hr_toolkit": True,
                "has_ai_resume_screening": True,
                "has_candidate_evaluation": True,
                "has_hiring_workflow_automation": True,
                "has_interview_scheduling": True,
                "has_offer_letter_management": True,
                "has_employee_onboarding": True,
                "has_task_management": True,
                "has_team_collaboration": True,
                "has_email_automation": True,
                "has_analytics_dashboard": True,
                "has_custom_workflows": True,
                "has_api_access": True,
                "has_third_party_integrations": True,
                "has_role_based_access": True,
                "has_ai_hiring_agent": True,
                "has_autonomous_ai_agents": True,
                "has_predictive_ai_analytics": True,
                "has_priority_support": True,
                "has_dedicated_manager": True,
            }
        ]
        
        for plan in plans_data:
            SubscriptionPlan.objects.create(**plan)



class UserSubscriptionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        subscription, created = UserSubscription.objects.get_or_create(
            user=request.user,
            defaults={
                "plan": SubscriptionPlan.objects.filter(price=0).first(),
                "status": "active"
            }
        )
        serializer = UserSubscriptionSerializer(subscription)
        data = serializer.data
        latest_payment = ManualPayment.objects.filter(user=request.user, subscription=subscription, plan=subscription.plan).order_by("-created_at").first()
        data["latest_payment"] = ManualPaymentSerializer(latest_payment, context={"request": request}).data if latest_payment else None
        return Response(data)

    def post(self, request):
        action = request.data.get("action")
        
        # Action to submit manual payment details and transaction screenshot
        if action == "submit_payment":
            try:
                subscription = UserSubscription.objects.get(user=request.user)
            except UserSubscription.DoesNotExist:
                return Response({"error": "No subscription record found. Please select a plan first."}, status=status.HTTP_400_BAD_REQUEST)

            plan = subscription.plan
            if not plan:
                return Response({"error": "No plan selected. Please choose a plan before submitting payment."}, status=status.HTTP_400_BAD_REQUEST)

            transaction_id = request.data.get("transaction_id")
            payment_method = request.data.get("payment_method")
            payment_type = request.data.get("payment_type", "new")
            upgrade_upi_or_phone = request.data.get("upgrade_upi_or_phone")
            screenshot = request.FILES.get("screenshot")

            if not transaction_id:
                return Response({"error": "transaction_id is required"}, status=status.HTTP_400_BAD_REQUEST)
            if not payment_method:
                return Response({"error": "payment_method is required"}, status=status.HTTP_400_BAD_REQUEST)
            if payment_type == "upgrade" and not upgrade_upi_or_phone:
                return Response({"error": "PhonePe Number or UPI ID is required when choosing an Upgrading Subscription."}, status=status.HTTP_400_BAD_REQUEST)
            if not screenshot:
                return Response({"error": "screenshot file is required"}, status=status.HTTP_400_BAD_REQUEST)

            # Prevent duplicate transaction submissions
            if ManualPayment.objects.filter(transaction_id=transaction_id.strip()).exists():
                return Response({"error": "This Transaction ID has already been submitted."}, status=status.HTTP_400_BAD_REQUEST)

            # Upload screenshot to ImageKit and optimize as WebP
            from maincore.imagekit_utils import ImageKitService
            import uuid
            import os

            ext = os.path.splitext(screenshot.name)[1].lower()
            convert_to_webp = ext in [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".jfif", ".avif"]

            upload_result = ImageKitService.upload_file(
                file_obj=screenshot,
                folder="/payment_proofs",
                file_name=f"verification_{request.user.id}_{uuid.uuid4().hex}",
                convert_to_webp=convert_to_webp
            )

            if not upload_result:
                return Response({"error": "Failed to upload transaction proof to ImageKit. Please try again."}, status=status.HTTP_502_BAD_GATEWAY)

            screenshot_url = upload_result["url"]

            # Create manual payment verification record
            payment = ManualPayment.objects.create(
                user=request.user,
                subscription=subscription,
                plan=plan,
                transaction_id=transaction_id.strip(),
                payment_method=payment_method.strip(),
                payment_type=payment_type,
                upgrade_upi_or_phone=upgrade_upi_or_phone.strip() if upgrade_upi_or_phone else None,
                screenshot=screenshot_url,
                status="pending"
            )

            # Ensure subscription is locked as pending until verified
            subscription.status = "pending"
            subscription.save()

            serializer = UserSubscriptionSerializer(subscription)
            data = serializer.data
            data["latest_payment"] = ManualPaymentSerializer(payment, context={"request": request}).data
            return Response(data, status=status.HTTP_201_CREATED)

        if action == "activate":
            try:
                subscription = UserSubscription.objects.get(user=request.user)
            except UserSubscription.DoesNotExist:
                return Response({"error": "no subscription activated"}, status=status.HTTP_400_BAD_REQUEST)
            
            if not subscription.plan or subscription.plan.price == 0:
                return Response({"error": "no subscription activated"}, status=status.HTTP_400_BAD_REQUEST)
            
            # Premium plans can only be verified and activated by an admin
            if subscription.plan.price > 0:
                return Response({"error": "Premium plans must be verified manually by an administrator. Please submit payment verification details."}, status=status.HTTP_400_BAD_REQUEST)

            subscription.status = "active"
            subscription.save()
            serializer = UserSubscriptionSerializer(subscription)
            return Response(serializer.data, status=status.HTTP_200_OK)

        plan_id = request.data.get("plan_id")
        if not plan_id:
            return Response({"error": "plan_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        plan = None
        # Try to find by UUID first
        try:
            import uuid
            from django.core.exceptions import ValidationError
            str_id = str(plan_id).strip()
            if len(str_id) in (32, 36):
                uuid_val = uuid.UUID(str_id)
                plan = SubscriptionPlan.objects.filter(id=uuid_val).first()
        except (ValueError, TypeError, ValidationError):
            pass

        # Try to find by slug
        if not plan:
            plan = SubscriptionPlan.objects.filter(slug=plan_id).first()

        # Try to find by plan_type
        if not plan:
            plan = SubscriptionPlan.objects.filter(plan_type=plan_id).first()

        if not plan:
            return Response({"error": "Plan not found"}, status=status.HTTP_404_NOT_FOUND)
            
        subscription, created = UserSubscription.objects.get_or_create(user=request.user)
        subscription.plan = plan
        if plan.price == 0:
            subscription.status = "active"
        else:
            subscription.status = "pending"
        subscription.save()
        
        serializer = UserSubscriptionSerializer(subscription)
        return Response(serializer.data, status=status.HTTP_200_OK)


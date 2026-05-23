from rest_framework import serializers
from .models import SubscriptionPlan, UserSubscription, ManualPayment

class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = "__all__"


class UserSubscriptionSerializer(serializers.ModelSerializer):
    plan_details = SubscriptionPlanSerializer(source="plan", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    is_payment_verified = serializers.SerializerMethodField()

    class Meta:
        model = UserSubscription
        fields = [
            "id",
            "user_email",
            "plan",
            "plan_details",
            "status",
            "start_date",
            "end_date",
            "is_payment_verified",
        ]

    def get_is_payment_verified(self, obj):
        # Free tier is always verified
        if not obj.plan or obj.plan.price == 0:
            return True
        
        # If premium, check if there is an approved ManualPayment record
        from .models import ManualPayment
        return ManualPayment.objects.filter(
            subscription=obj,
            plan=obj.plan,
            status="approved"
        ).exists()


class ManualPaymentSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = ManualPayment
        fields = [
            "id",
            "user_email",
            "plan",
            "plan_name",
            "transaction_id",
            "payment_method",
            "payment_type",
            "upgrade_upi_or_phone",
            "screenshot",
            "status",
            "notes",
            "created_at",
        ]


from rest_framework import serializers
from .models import UserCredit, CreditTransaction

class UserCreditSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserCredit
        fields = ("balance", "last_allocated_plan_type", "updated_at")

class CreditTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CreditTransaction
        fields = ("id", "amount", "activity_type", "description", "created_at")

class UserCreditAdminSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = UserCredit
        fields = ("id", "user", "user_email", "balance", "last_allocated_plan_type", "created_at", "updated_at")


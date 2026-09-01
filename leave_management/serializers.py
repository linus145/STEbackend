from rest_framework import serializers
from leave_management.models import LeaveType, LeaveRequest, LeaveBalance
from employees.models import Employee
from employees.serializers import EmployeeSerializer


class LeaveTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveType
        fields = "__all__"
        read_only_fields = ["id", "startup", "organization", "company"]


class LeaveRequestSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeSerializer(source="employee", read_only=True)
    leave_type_detail = LeaveTypeSerializer(source="leave_type", read_only=True)
    employee_name = serializers.SerializerMethodField()
    leave_type_name = serializers.CharField(source="leave_type.name", read_only=True)
    total_days = serializers.SerializerMethodField()

    class Meta:
        model = LeaveRequest
        fields = "__all__"
        read_only_fields = [
            "id",
            "status",
            "approved_by",
            "comment",
            "created_at",
            "updated_at",
            "employee",
            "startup",
            "organization",
            "company",
        ]

    def get_employee_name(self, obj):
        if obj.employee:
            return f"{obj.employee.first_name} {obj.employee.last_name}"
        return "Employee"

    def get_total_days(self, obj):
        if obj.start_date and obj.end_date:
            return (obj.end_date - obj.start_date).days + 1
        return 0


class LeaveBalanceEmployeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = ["id", "first_name", "last_name", "email", "employee_id"]


class LeaveBalanceSerializer(serializers.ModelSerializer):
    leave_type_name = serializers.CharField(source="leave_type.name", read_only=True)
    leave_type_detail = LeaveTypeSerializer(source="leave_type", read_only=True)
    employee_detail = LeaveBalanceEmployeeSerializer(source="employee", read_only=True)

    class Meta:
        model = LeaveBalance
        fields = [
            "id",
            "employee",
            "employee_detail",
            "leave_type",
            "leave_type_name",
            "leave_type_detail",
            "year",
            "total_days",
            "used_days",
            "remaining_days",
        ]
        read_only_fields = ["id", "remaining_days"]

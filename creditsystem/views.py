"""
AI Credit System Cost & Burn Rates:
- Full Hiring Workflow: 150 credits / run
- Recruitment Agent: 10 credits / run
- Browser Agent Step: 0.1 credits / step
- Resume Screening: 1 credit / resume
- Question Generation: 2 credits / question
- Question Evaluation: 1 credit / question
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from .models import UserCredit, CreditTransaction, ManualCreditVerification
from .serializers import UserCreditSerializer, CreditTransactionSerializer, UserCreditAdminSerializer
from .utils import check_and_get_user_credit

class UserCreditViewSet(viewsets.ModelViewSet):
    """
    Administrative ViewSet for CRUD operations on UserCredit models.
    Only accessible by staff/admin users.
    """
    queryset = UserCredit.objects.select_related("user").all()
    serializer_class = UserCreditAdminSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]


class UserCreditBalanceView(APIView):
    """
    API View to retrieve the authenticated user's credit balance and subscription tier limit.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user_credit = check_and_get_user_credit(request.user)
            serializer = UserCreditSerializer(user_credit)
            
            # Map plan types to their monthly limits
            plan_limits = {
                "free": 100,
                "basic": 500,
                "growth": 1000,
                "enterprise": 1500
            }
            plan_limit = plan_limits.get(user_credit.last_allocated_plan_type, 100)
            
            data = serializer.data
            data["plan_limit"] = plan_limit
            
            return Response({
                "status": "success",
                "message": "Credit balance retrieved successfully.",
                "data": data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                "status": "error",
                "message": str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

class CreditTransactionHistoryView(APIView):
    """
    API View to retrieve the transaction history of the authenticated user.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            # Trigger self-heal check if user_credit doesn't exist yet
            check_and_get_user_credit(request.user)
            
            transactions = CreditTransaction.objects.filter(user=request.user).order_by("-created_at")
            serializer = CreditTransactionSerializer(transactions, many=True)
            
            return Response({
                "status": "success",
                "message": "Credit transaction history retrieved successfully.",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                "status": "error",
                "message": str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


class PurchaseCreditsView(APIView):
    """
    API View to submit payment verification details for purchasing AI credits.
    The request is recorded as pending verification and credits are allocated upon verification.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            amount = request.data.get("amount")
            transaction_id = request.data.get("transaction_id")
            payment_method = request.data.get("payment_method", "UPI/Online")

            try:
                amount_val = float(amount) if amount is not None else 0.0
            except (ValueError, TypeError):
                amount_val = 0.0

            if amount_val <= 0:
                return Response({
                    "status": "error",
                    "message": "Valid credit amount is required."
                }, status=status.HTTP_400_BAD_REQUEST)

            if not transaction_id or not str(transaction_id).strip():
                return Response({
                    "status": "error",
                    "message": "Payment Transaction ID / Reference Number is required for verification."
                }, status=status.HTTP_400_BAD_REQUEST)

            transaction_id = str(transaction_id).strip()
            amount = amount_val
            package_name = request.data.get("package_name", "Credit Top-up")
            upi_or_phone = request.data.get("upi_or_phone", "")

            # Check if transaction ID was already submitted
            existing_tx = CreditTransaction.objects.filter(
                metadata__transaction_id=transaction_id
            ).first()
            if existing_tx:
                tx_status = existing_tx.metadata.get("status", "pending") if existing_tx.metadata else "pending"
                if tx_status == "approved":
                    return Response({
                        "status": "error",
                        "message": "This Transaction ID has already been verified and credited."
                    }, status=status.HTTP_400_BAD_REQUEST)
                return Response({
                    "status": "pending_verification",
                    "message": "This Transaction ID was already submitted and is currently pending verification.",
                    "data": {
                        "transaction_id": transaction_id,
                        "status": "pending",
                        "credits_requested": float(existing_tx.amount)
                    }
                }, status=status.HTTP_200_OK)

            # Record pending credit transaction (balance is NOT modified until verification)
            description = (
                f"Pending Verification - Txn ID: {transaction_id} ({package_name}) via {payment_method}. "
                f"{amount:.0f} credits will be added after payment verification."
            )

            screenshot_file = request.FILES.get("screenshot")
            screenshot_url = request.data.get("screenshot", "")

            if screenshot_file:
                try:
                    from maincore.imagekit_utils import ImageKitService
                    import uuid
                    import os

                    ext = os.path.splitext(screenshot_file.name)[1].lower()
                    convert_to_webp = ext in [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".jfif", ".avif"]

                    upload_result = ImageKitService.upload_file(
                        file_obj=screenshot_file,
                        folder="/credit_payment_proofs",
                        file_name=f"credit_verification_{request.user.id}_{uuid.uuid4().hex}",
                        convert_to_webp=convert_to_webp
                    )
                    if upload_result and "url" in upload_result:
                        screenshot_url = upload_result["url"]
                except Exception as img_err:
                    print(f"ImageKit upload error: {img_err}")

            screenshot = screenshot_url

            tx = CreditTransaction.objects.create(
                user=request.user,
                activity_type="purchase",
                amount=amount,
                description=description,
                metadata={
                    "transaction_id": transaction_id,
                    "payment_method": payment_method,
                    "upi_or_phone": upi_or_phone,
                    "package_name": package_name,
                    "screenshot": screenshot,
                    "status": "pending"
                }
            )

            # Record in ManualCreditVerification backend table for admin review & approval
            ManualCreditVerification.objects.create(
                user=request.user,
                credits_requested=amount,
                package_name=package_name,
                amount_paid=f"₹{int(amount / 1.15)}" if amount else "",
                transaction_id=transaction_id,
                payment_method=payment_method,
                upi_or_phone=upi_or_phone,
                screenshot=screenshot,
                status="pending"
            )

            # Auto-verify if auto_verify flag is explicitly provided
            auto_verify = request.data.get("auto_verify", False)
            if auto_verify:
                ver = ManualCreditVerification.objects.filter(transaction_id=transaction_id).first()
                if ver:
                    ver.status = "approved"
                    ver.save()

                user_credit = check_and_get_user_credit(request.user)
                serializer = UserCreditSerializer(user_credit)
                data = serializer.data
                plan_limits = {"free": 100, "basic": 500, "growth": 1000, "enterprise": 1500}
                data["plan_limit"] = plan_limits.get(user_credit.last_allocated_plan_type, 100)

                return Response({
                    "status": "success",
                    "message": f"Payment verified! Successfully added {amount:.0f} credits to your account.",
                    "data": data
                }, status=status.HTTP_200_OK)

            return Response({
                "status": "pending_verification",
                "message": f"Payment verification submitted for Txn ID {transaction_id}. Credits ({amount:.0f}) will be added after administrator verification.",
                "data": {
                    "transaction_id": transaction_id,
                    "credits_requested": amount,
                    "status": "pending"
                }
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({
                "status": "error",
                "message": str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


class VerifyCreditPaymentView(APIView):
    """
    API View to verify a pending credit payment transaction and allocate credits to the user.
    Only accessible by administrator staff.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            if not (request.user.is_staff or request.user.is_superuser):
                return Response({
                    "status": "error",
                    "message": "Only administrator staff can verify and approve credit payment transactions."
                }, status=status.HTTP_403_FORBIDDEN)

            transaction_id = request.data.get("transaction_id")
            action = request.data.get("action", "approve")  # "approve" or "reject"

            if not transaction_id or not str(transaction_id).strip():
                return Response({
                    "status": "error",
                    "message": "transaction_id is required."
                }, status=status.HTTP_400_BAD_REQUEST)

            transaction_id = str(transaction_id).strip()

            ver = ManualCreditVerification.objects.filter(transaction_id=transaction_id).first()
            tx = CreditTransaction.objects.filter(metadata__transaction_id=transaction_id).first()

            if not ver and not tx:
                return Response({
                    "status": "error",
                    "message": f"No pending payment found with Transaction ID '{transaction_id}'."
                }, status=status.HTTP_404_NOT_FOUND)

            if ver and ver.status == "approved":
                return Response({
                    "status": "error",
                    "message": "This payment transaction has already been verified and approved."
                }, status=status.HTTP_400_BAD_REQUEST)

            if action == "reject":
                if ver:
                    ver.status = "rejected"
                    ver.save()
                if tx:
                    tx.metadata["status"] = "rejected"
                    tx.description = f"Payment Verification Rejected - Txn ID: {transaction_id}."
                    tx.save()
                return Response({
                    "status": "success",
                    "message": "Payment verification request was rejected."
                }, status=status.HTTP_200_OK)

            # Approve payment: Updating ManualCreditVerification status='approved' automatically
            # credits the user's UserCredit balance & updates CreditTransaction log via save() signal/method!
            if ver:
                ver.status = "approved"
                ver.save()
            elif tx:
                user_credit = check_and_get_user_credit(tx.user)
                old_balance = float(user_credit.balance)
                amount = float(tx.amount)
                user_credit.balance = float(user_credit.balance) + amount
                user_credit.save()

                package_name = tx.metadata.get("package_name", "Credit Top-up") if tx.metadata else "Credit Top-up"
                payment_method = tx.metadata.get("payment_method", "UPI") if tx.metadata else "UPI"

                tx.metadata["status"] = "approved"
                tx.description = (
                    f"Payment Verified & Approved - Txn ID: {transaction_id} ({package_name}) via {payment_method}. "
                    f"Balance increased from {old_balance:.0f} to {user_credit.balance:.0f}."
                )
                tx.save()

            target_user = ver.user if ver else tx.user
            user_credit = check_and_get_user_credit(target_user)
            serializer = UserCreditSerializer(user_credit)
            data = serializer.data
            plan_limits = {"free": 100, "basic": 500, "growth": 1000, "enterprise": 1500}
            data["plan_limit"] = plan_limits.get(user_credit.last_allocated_plan_type, 100)

            return Response({
                "status": "success",
                "message": f"Payment verified & approved! Credits added to account balance.",
                "data": data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                "status": "error",
                "message": str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


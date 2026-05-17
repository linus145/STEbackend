from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from notifications.models import Notification
from notifications.serializers import NotificationSerializer

class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    dashboard_filter = None

    def get_queryset(self):
        queryset = Notification.objects.filter(recipient=self.request.user)
        if self.dashboard_filter:
            queryset = queryset.filter(dashboard=self.dashboard_filter)
        else:
            dashboard = self.request.query_params.get('dashboard')
            if dashboard:
                queryset = queryset.filter(dashboard=dashboard.upper())
        return queryset

class MarkNotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            notification = Notification.objects.get(pk=pk, recipient=request.user)
            notification.is_read = True
            notification.save()
            return Response({'status': 'read'}, status=status.HTTP_200_OK)
        except Notification.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

class MarkAllReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        dashboard = request.query_params.get('dashboard') or request.data.get('dashboard')
        qs = Notification.objects.filter(recipient=request.user, is_read=False)
        if dashboard:
            qs = qs.filter(dashboard=dashboard.upper())
        qs.update(is_read=True)
        return Response({'status': 'all marked read'}, status=status.HTTP_200_OK)

class DeleteAllNotificationsView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        dashboard = request.query_params.get('dashboard')
        qs = Notification.objects.filter(recipient=request.user)
        if dashboard:
            qs = qs.filter(dashboard=dashboard.upper())
        qs.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class NotificationUnreadCountsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_unread = Notification.objects.filter(recipient=request.user, dashboard='USER', is_read=False).count()
        recruiter_unread = Notification.objects.filter(recipient=request.user, dashboard='RECRUITER', is_read=False).count()
        interview_unread = Notification.objects.filter(recipient=request.user, dashboard='INTERVIEW', is_read=False).count()
        hr_unread = Notification.objects.filter(recipient=request.user, dashboard='HR', is_read=False).count()
        
        return Response({
            'USER': user_unread,
            'RECRUITER': recruiter_unread,
            'INTERVIEW': interview_unread,
            'HR': hr_unread,
            'total': user_unread + recruiter_unread + interview_unread + hr_unread
        }, status=status.HTTP_200_OK)

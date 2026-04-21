from django.urls import path
from .views import StartupListView, MyStartupsView, StartupDetailView

app_name = 'startups'

urlpatterns = [
    path('', StartupListView.as_view(), name='startup_list'),
    path('me/', MyStartupsView.as_view(), name='my_startups'), # GET and POST custom startups
    path('<uuid:startup_id>/', StartupDetailView.as_view(), name='startup_detail'), # GET, PUT, DELETE
]

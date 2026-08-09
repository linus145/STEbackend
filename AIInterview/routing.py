from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r"ws/webrtc/(?P<room_id>[A-Za-z0-9_-]+)/$", consumers.WebRTCSignalingConsumer.as_asgi()),
    re_path(r"ws/azure-voice/(?P<exam_token>[0-9a-f-]+)/(?P<round_id>[0-9a-f-]+)/$", consumers.AzureVoiceLiveConsumer.as_asgi()),
]

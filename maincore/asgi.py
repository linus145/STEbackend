"""
ASGI config for maincore project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'maincore.settings')

django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from maincore.middleware import JWTAuthMiddleware
from chat.routing import websocket_urlpatterns as chat_ws_urlpatterns
from AIInterview.routing import websocket_urlpatterns as webrtc_ws_urlpatterns

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddleware(
        URLRouter(
            # WebRTC signaling — no auth needed (consumer accepts all, room is UUID-secured)
            webrtc_ws_urlpatterns
            +
            # Chat — JWT auth required (consumer checks scope['user'].is_authenticated)
            chat_ws_urlpatterns
        )
    ),
})

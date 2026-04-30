from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from django.conf import settings

User = get_user_model()


@database_sync_to_async
def get_user_from_token(token):
    """Validate a JWT access token and return the corresponding user."""
    try:
        from rest_framework_simplejwt.tokens import AccessToken
        access_token = AccessToken(token)
        user_id = access_token["user_id"]
        return User.objects.get(id=user_id)
    except Exception:
        return AnonymousUser()


@database_sync_to_async
def get_user_from_ticket(ticket_id):
    """Validate a one-time ticket and return the user."""
    from useraccounts.models import WsTicket
    try:
        ticket = WsTicket.objects.get(id=ticket_id)
        if ticket.is_valid():
            ticket.is_used = True
            ticket.save()
            return ticket.user
    except Exception:
        pass
    return AnonymousUser()


class JWTAuthMiddleware:
    """
    Django Channels middleware that authenticates WebSocket connections
    using either:
      1. One-time ticket (Secure): ws://host/ws/chat/?ticket=<uuid>
      2. HttpOnly Cookie (Fallback): uses AUTH_COOKIE
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        from urllib.parse import parse_qs
        from http.cookies import SimpleCookie

        user = AnonymousUser()

        # 1. Check for one-time ticket (Highest Security)
        query_string = scope.get("query_string", b"").decode("utf-8")
        query_params = parse_qs(query_string)
        ticket_id = query_params.get("ticket", [None])[0] or query_params.get("token", [None])[0]

        if ticket_id:
            user = await get_user_from_ticket(ticket_id)

        # 2. Fallback to Cookie header if ticket is missing or invalid
        if user.is_anonymous:
            headers = dict(scope.get("headers", []))
            cookie_header = headers.get(b"cookie", b"").decode("utf-8")
            if cookie_header:
                cookie = SimpleCookie()
                cookie.load(cookie_header)
                cookie_name = settings.SIMPLE_JWT.get("AUTH_COOKIE", "access_token")
                if cookie_name in cookie:
                    token = cookie[cookie_name].value
                    user = await get_user_from_token(token)

        scope["user"] = user
        return await self.inner(scope, receive, send)

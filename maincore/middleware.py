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


class JWTAuthMiddleware:
    """
    Django Channels middleware that authenticates WebSocket connections
    using JWT tokens from either:
      1. Query string: ws://host/ws/chat/<id>/?token=<jwt>
      2. Cookie header: uses the AUTH_COOKIE name from SIMPLE_JWT settings
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        from urllib.parse import parse_qs
        from http.cookies import SimpleCookie

        token = None

        # 1. Query string  (?token=...)
        query_string = scope.get("query_string", b"").decode("utf-8")
        query_params = parse_qs(query_string)
        token = query_params.get("token", [None])[0]

        # 2. Cookie header
        if not token:
            headers = dict(scope.get("headers", []))
            cookie_header = headers.get(b"cookie", b"").decode("utf-8")
            if cookie_header:
                cookie = SimpleCookie()
                cookie.load(cookie_header)
                cookie_name = settings.SIMPLE_JWT.get("AUTH_COOKIE", "access_token")
                if cookie_name in cookie:
                    token = cookie[cookie_name].value

        if token:
            scope["user"] = await get_user_from_token(token)
        else:
            scope["user"] = AnonymousUser()

        return await self.inner(scope, receive, send)

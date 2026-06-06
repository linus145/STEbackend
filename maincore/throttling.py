import logging
import json
from rest_framework.throttling import SimpleRateThrottle

logger = logging.getLogger('throttling')

class LoggingSimpleRateThrottle(SimpleRateThrottle):
    """
    Base throttle class that logs structured data in JSON format when a request is throttled.
    """
    def allow_request(self, request, view):
        allowed = super().allow_request(request, view)
        if not allowed:
            self.log_throttled_request(request)
        return allowed

    def log_throttled_request(self, request):
        user = request.user
        user_id = str(user.id) if user and user.is_authenticated else "anonymous"
        
        # Determine client IP address
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(',')[0].strip()
        else:
            ip_address = request.META.get('REMOTE_ADDR')
            
        endpoint = request.path
        method = request.method
        
        # Retrieve rate info and history details
        rate = getattr(self, 'rate', 'unknown')
        scope = getattr(self, 'scope', 'unknown')
        history = getattr(self, 'history', [])
        request_count = len(history) + 1  # includes the current request exceeding the limit
        
        log_data = {
            "endpoint": endpoint,
            "method": method,
            "user_id": user_id,
            "ip_address": ip_address,
            "throttle_scope": scope,
            "throttle_limit": rate,
            "request_count": request_count,
        }
        
        logger.warning(f"RATE_LIMIT_EXCEEDED: {json.dumps(log_data)}")


class UserBurstThrottle(LoggingSimpleRateThrottle):
    scope = 'user_burst'

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = request.user.pk
        else:
            ident = self.get_ident(request)

        return self.cache_format % {
            'scope': self.scope,
            'ident': ident
        }


class UserSustainedThrottle(LoggingSimpleRateThrottle):
    scope = 'user_sustained'

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = request.user.pk
        else:
            ident = self.get_ident(request)

        return self.cache_format % {
            'scope': self.scope,
            'ident': ident
        }


class AnonBurstThrottle(LoggingSimpleRateThrottle):
    scope = 'anon_burst'

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            return None  # Only throttle anonymous requests

        return self.cache_format % {
            'scope': self.scope,
            'ident': self.get_ident(request)
        }


class AnonSustainedThrottle(LoggingSimpleRateThrottle):
    scope = 'anon_sustained'

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            return None  # Only throttle anonymous requests

        return self.cache_format % {
            'scope': self.scope,
            'ident': self.get_ident(request)
        }


class LoginBurstThrottle(LoggingSimpleRateThrottle):
    scope = 'login_burst'

    def get_cache_key(self, request, view):
        if request.method != 'POST':
            return None

        ip = self.get_ident(request)
        email = request.data.get('email', '').strip().lower() if hasattr(request, 'data') else ''
        
        return self.cache_format % {
            'scope': self.scope,
            'ident': f"{ip}:{email}" if email else ip
        }


class LoginSustainedThrottle(LoggingSimpleRateThrottle):
    scope = 'login_sustained'

    def get_cache_key(self, request, view):
        if request.method != 'POST':
            return None

        ip = self.get_ident(request)
        email = request.data.get('email', '').strip().lower() if hasattr(request, 'data') else ''
        
        return self.cache_format % {
            'scope': self.scope,
            'ident': f"{ip}:{email}" if email else ip
        }


class OTPRequestThrottle(LoggingSimpleRateThrottle):
    scope = 'otp_request'

    def get_cache_key(self, request, view):
        return self.cache_format % {
            'scope': self.scope,
            'ident': self.get_ident(request)
        }


class OTPVerifyThrottle(LoggingSimpleRateThrottle):
    scope = 'otp_verify'

    def get_cache_key(self, request, view):
        return self.cache_format % {
            'scope': self.scope,
            'ident': self.get_ident(request)
        }


class LogViolationThrottle(LoggingSimpleRateThrottle):
    scope = 'log_violation'

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = request.user.pk
        else:
            ident = self.get_ident(request)

        return self.cache_format % {
            'scope': self.scope,
            'ident': ident
        }


class CodeExecutionThrottle(LoggingSimpleRateThrottle):
    scope = 'code_execution'

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = request.user.pk
        else:
            ident = self.get_ident(request)

        return self.cache_format % {
            'scope': self.scope,
            'ident': ident
        }

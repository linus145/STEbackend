from rest_framework import status
from rest_framework.response import Response

class ResponseMixin:
    """Standardized JSON response helper."""
    def build_response(self, status_msg, message, data=None, status_code=status.HTTP_200_OK):
        return Response(
            {"status": status_msg, "message": message, "data": data if data is not None else {}},
            status=status_code,
        )


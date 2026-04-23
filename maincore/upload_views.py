import logging
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser

from maincore.imagekit_utils import ImageKitService

logger = logging.getLogger(__name__)

# Maximum file size: 10MB
MAX_FILE_SIZE = 10 * 1024 * 1024

ALLOWED_IMAGE_TYPES = [
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/bmp",
    "image/tiff",
    "image/avif",
]

ALLOWED_VIDEO_TYPES = [
    "video/mp4",
    "video/webm",
    "video/quicktime",
]


class ImageUploadView(APIView):
    """
    Server-side image upload endpoint.
    Accepts multipart/form-data with a 'file' field.
    Uploads to ImageKit and returns the CDN URL.

    POST /api/upload/image/
    Body: multipart/form-data
      - file: (required) The image file to upload
      - folder: (optional) Target folder in ImageKit (default: /uploads)

    Response:
      {
        "image_url": "https://ik.imagekit.io/...",
        "file_id": "...",
        "file_name": "..."
      }
    """

    permission_classes = (IsAuthenticated,)
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
        # 1. Validate file presence
        file = request.FILES.get("file")
        if not file:
            logger.warning(f"Upload attempt with no file by user {request.user.id}")
            return Response(
                {"error": "No file provided. Include a 'file' field in multipart/form-data."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2. Validate file size
        if file.size > MAX_FILE_SIZE:
            return Response(
                {
                    "error": f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB.",
                    "max_size_bytes": MAX_FILE_SIZE,
                    "received_size_bytes": file.size,
                },
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        # 3. Validate file type
        content_type = file.content_type
        all_allowed = ALLOWED_IMAGE_TYPES + ALLOWED_VIDEO_TYPES
        if content_type not in all_allowed:
            return Response(
                {
                    "error": f"Unsupported file type: {content_type}",
                    "allowed_types": all_allowed,
                },
                status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            )

        # 4. Determine folder
        folder = request.data.get("folder", "/uploads")
        if not folder.startswith("/"):
            folder = "/" + folder

        # 5. Determine if WebP conversion should apply (skip for videos and GIFs)
        convert_to_webp = content_type in ALLOWED_IMAGE_TYPES and content_type not in [
            "image/gif",
            "image/webp",
        ]

        # 6. Upload to ImageKit
        result = ImageKitService.upload_file(
            file_obj=file,
            folder=folder,
            file_name=file.name,
            convert_to_webp=convert_to_webp,
        )

        if result is None:
            logger.error(f"ImageKit upload failed for user {request.user.id}, file: {file.name}")
            return Response(
                {"error": "Image upload failed. Please try again or contact support."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        logger.info(
            f"Upload success by user {request.user.id}: {result['url']}"
        )

        return Response(
            {
                "image_url": result["url"],
                "file_id": result.get("file_id", ""),
                "file_name": result.get("name", ""),
            },
            status=status.HTTP_200_OK,
        )

import os
import logging
from io import BytesIO
from imagekitio import ImageKit
from django.conf import settings

logger = logging.getLogger(__name__)


class ImageKitService:
    """
    Centralized ImageKit service for all server-side image operations.
    Uses the ImageKit Python SDK v5.x (private_key-only constructor).
    """

    _instance = None

    @classmethod
    def get_instance(cls):
        """Returns a singleton ImageKit client instance."""
        if cls._instance is None:
            if not all(
                [
                    settings.IMAGEKIT_PUBLIC_KEY,
                    settings.IMAGEKIT_PRIVATE_KEY,
                    settings.IMAGEKIT_URL_ENDPOINT,
                ]
            ):
                logger.error(
                    "ImageKit credentials missing. Check IMAGEKIT_PUBLIC_KEY, "
                    "IMAGEKIT_PRIVATE_KEY, and IMAGEKIT_URL_ENDPOINT in .env"
                )
                return None

            cls._instance = ImageKit(private_key=settings.IMAGEKIT_PRIVATE_KEY)
            logger.info("ImageKit client initialized successfully.")
        return cls._instance

    @staticmethod
    def get_auth_params():
        """Returns authentication parameters for client-side uploads (if ever needed)."""
        ik = ImageKitService.get_instance()
        if not ik:
            return None
        return ik.helper.get_authentication_parameters()

    @staticmethod
    def upload_file(file_obj, folder="/uploads", file_name=None, convert_to_webp=True):
        """
        Uploads a file (from request.FILES) to ImageKit.

        Args:
            file_obj: Django UploadedFile (from request.FILES)
            folder: Target folder in ImageKit (e.g. "/posts", "/profiles")
            file_name: Override filename (optional)
            convert_to_webp: Convert images to WebP before upload (default True)

        Returns:
            dict with 'url', 'file_id', 'name' on success
            None on failure
        """
        ik = ImageKitService.get_instance()
        if not ik:
            logger.error("ImageKit client not available. Upload aborted.")
            return None

        try:
            # Read file content
            file_content = file_obj.read()
            original_name = file_name or file_obj.name
            ext = os.path.splitext(original_name)[1].lower()

            # Convert images to WebP for optimization
            image_extensions = [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".jfif", ".avif"]
            if convert_to_webp and ext in image_extensions:
                converted_content, new_name = ImageKitService._convert_to_webp(
                    file_content
                )
                if converted_content is not None:
                    file_content = converted_content
                    original_name = os.path.splitext(original_name)[0] + ".webp"

            # Upload via SDK (v5.x: ik.files.upload expects bytes, IOBase, PathLike, or tuple)
            response = ik.files.upload(
                file=file_content,
                file_name=original_name,
                folder=folder,
                use_unique_file_name=True,
            )

            # SDK v5.x returns an UploadResponse object
            if response and hasattr(response, "url"):
                logger.info(
                    f"ImageKit upload success: {response.url} (file_id: {response.file_id})"
                )
                return {
                    "url": response.url,
                    "file_id": response.file_id,
                    "name": response.name,
                }

            # Fallback: check response_metadata for errors
            if hasattr(response, "response_metadata"):
                logger.error(
                    f"ImageKit upload error: {response.response_metadata}"
                )

            return None

        except Exception as e:
            logger.exception(f"ImageKit upload exception: {e}")
            return None

    @staticmethod
    def _convert_to_webp(file_bytes, quality=80):
        """
        Converts image bytes to WebP format.
        Returns (converted_bytes, new_filename) or (None, None) on failure.
        """
        from PIL import Image

        try:
            img = Image.open(BytesIO(file_bytes))

            # Handle transparency modes
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGBA")
            elif img.mode != "RGB":
                img = img.convert("RGB")

            buffer = BytesIO()
            img.save(buffer, format="WEBP", quality=quality)
            return buffer.getvalue(), "image.webp"

        except Exception as e:
            logger.warning(f"WebP conversion failed, using original: {e}")
            return None, None

    @staticmethod
    def delete_file(file_url):
        """
        Deletes a file from ImageKit given its full URL.
        Searches by filename and folder path to find the file_id, then deletes.
        """
        ik = ImageKitService.get_instance()
        if not ik or not file_url:
            return False

        try:
            # Extract relative path from full URL
            endpoint = settings.IMAGEKIT_URL_ENDPOINT.rstrip("/")
            if not file_url.startswith(endpoint):
                logger.warning(
                    f"URL doesn't match endpoint, skipping delete: {file_url}"
                )
                return False

            path_val = file_url[len(endpoint) :].lstrip("/")

            folder = os.path.dirname(path_val)
            if not folder.startswith("/"):
                folder = "/" + folder
            filename = os.path.basename(path_val)

            # Search for file in ImageKit using the REST API
            import httpx

            search_url = "https://api.imagekit.io/v1/files"
            response = httpx.get(
                search_url,
                params={"name": filename, "path": folder},
                auth=(settings.IMAGEKIT_PRIVATE_KEY, ""),
                timeout=10.0,
            )

            if response.status_code == 200:
                file_list = response.json()
                for f in file_list:
                    if f.get("name") == filename and f.get("fileId"):
                        ik.files.delete(f["fileId"])
                        logger.info(f"ImageKit file deleted: {file_url}")
                        return True

        except Exception as e:
            logger.warning(f"ImageKit delete failed for {file_url}: {e}")

        return False

    @staticmethod
    def convert_to_webp(content, quality=80):
        """
        Legacy compatibility wrapper for convert_to_webp.
        Accepts a file-like object instead of raw bytes.
        """
        from PIL import Image
        from django.core.files.base import ContentFile

        try:
            img = Image.open(content)

            if img.mode in ("RGBA", "LA"):
                pass
            elif img.mode != "RGB":
                img = img.convert("RGB")

            buffer = BytesIO()
            img.save(buffer, format="WEBP", quality=quality)
            buffer.seek(0)

            return ContentFile(buffer.read()), "image.webp"
        except Exception as e:
            logger.warning(f"WebP conversion failed: {e}")
            if hasattr(content, "seek"):
                content.seek(0)
            return content, None

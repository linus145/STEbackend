import os
import logging
from io import BytesIO
from imagekitio import ImageKit
from django.conf import settings

logger = logging.getLogger(__name__)

# Complete list of supported image formats for Endpoint 1
IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".svg",
    ".bmp",
    ".ico",
    ".tiff",
    ".tif",
    ".avif",
    ".heic",
    ".heif",
    ".jfif",
}


class ImageKitService:
    """
    Centralized ImageKit service for all server-side file and image operations.
    Dual-endpoint routing:
      - 'image' (Endpoint 1): All image types (.jpg, .png, .webp, .svg, .gif, .bmp, .ico, .tiff, etc.)
      - 'media' (Endpoint 2): All PDFs, payslips, Word/Excel docs, text files, archives & other media
    """

    _image_instance = None
    _media_instance = None
    _company_instance = None

    @classmethod
    def get_instance(cls, service_type="image"):
        """
        Returns a singleton ImageKit client instance.
        service_type:
          - 'image' (Endpoint 1): General images
          - 'media' / 'pdf' (Endpoint 2): PDFs & documents
          - 'company' / 'company_post' (Endpoint 3): Company profile & post images
        """
        if service_type in ("company", "company_post", "company_media", "company_page"):
            if cls._company_instance is None:
                private_key = getattr(settings, "IMAGEKIT_PRIVATE_KEY3", "") or getattr(
                    settings, "IMAGEKIT_PRIVATE_KEY", ""
                )
                if not private_key:
                    logger.error(
                        "ImageKit Company (Endpoint 3) credentials missing in .env"
                    )
                    return None

                cls._company_instance = ImageKit(private_key=private_key)
                logger.info("ImageKit Company client (Endpoint 3) initialized successfully.")
            return cls._company_instance

        if service_type in ("media", "pdf", "docs", "document"):
            if cls._media_instance is None:
                private_key = getattr(settings, "IMAGEKIT_PRIVATE_KEY2", "") or getattr(
                    settings, "IMAGEKIT_PRIVATE_KEY", ""
                )
                endpoint = getattr(settings, "IMAGEKIT_URL_ENDPOINT2", "") or getattr(
                    settings, "IMAGEKIT_URL_ENDPOINT", ""
                )

                if not private_key:
                    logger.error(
                        "ImageKit Media (Endpoint 2) credentials missing in .env"
                    )
                    return None

                cls._media_instance = ImageKit(private_key=private_key)
                logger.info("ImageKit Media/PDF client (Endpoint 2) initialized successfully.")
            return cls._media_instance

        # Default: Image client (Endpoint 1)
        if cls._image_instance is None:
            private_key = getattr(settings, "IMAGEKIT_PRIVATE_KEY", "")
            endpoint = getattr(settings, "IMAGEKIT_URL_ENDPOINT", "")

            if not private_key:
                logger.error(
                    "ImageKit Image (Endpoint 1) credentials missing in .env"
                )
                return None

            cls._image_instance = ImageKit(private_key=private_key)
            logger.info("ImageKit Image client (Endpoint 1) initialized successfully.")
        return cls._image_instance

    @classmethod
    def get_media_instance(cls):
        """Helper to directly get media/PDF client instance (Endpoint 2)."""
        return cls.get_instance(service_type="media")

    @classmethod
    def get_company_instance(cls):
        """Helper to directly get company client instance (Endpoint 3)."""
        return cls.get_instance(service_type="company")

    @staticmethod
    def get_endpoint(service_type="image"):
        """Returns the CDN URL endpoint string based on service_type."""
        if service_type in ("company", "company_post", "company_media", "company_page"):
            return getattr(settings, "IMAGEKIT_URL_ENDPOINT3", "") or getattr(
                settings, "IMAGEKIT_URL_ENDPOINT", ""
            )
        if service_type in ("media", "pdf", "docs", "document"):
            return getattr(settings, "IMAGEKIT_URL_ENDPOINT2", "") or getattr(
                settings, "IMAGEKIT_URL_ENDPOINT", ""
            )
        return getattr(settings, "IMAGEKIT_URL_ENDPOINT", "")

    @staticmethod
    def is_image(filename):
        """
        Returns True if the file has any recognized image extension.
        """
        if not filename:
            return False
        ext = os.path.splitext(filename)[1].lower()
        return ext in IMAGE_EXTENSIONS

    @staticmethod
    def is_document_or_media(filename, folder=""):
        """
        Returns True if the file is a PDF or other document/media (routes to Endpoint 2).
        Any file that is not explicitly an image routes to Endpoint 2.
        """
        return not ImageKitService.is_image(filename)

    @staticmethod
    def upload_file(
        file_obj,
        folder="/uploads",
        file_name=None,
        convert_to_webp=True,
        is_media_or_doc=None,
    ):
        """
        Uploads a file (bytes or Django UploadedFile) to the appropriate ImageKit endpoint.

        Args:
            file_obj: Django UploadedFile or file-like / bytes object
            folder: Target folder in ImageKit (e.g. "/payslips", "/profiles")
            file_name: Override filename (optional)
            convert_to_webp: Convert raster images to WebP before upload (default True)
            is_media_or_doc: Explicitly override routing to media/PDF (Endpoint 2)

        Returns:
            dict with 'url', 'file_id', 'name' on success, or None on failure
        """
        try:
            # Resolve filename
            original_name = (
                file_name
                or getattr(file_obj, "name", "file")
                or "file"
            )
            ext = os.path.splitext(original_name)[1].lower()

            # Determine routing: Company (Endpoint 3) vs PDF/Doc (Endpoint 2) vs Image (Endpoint 1)
            if folder.startswith("/company") or is_media_or_doc == "company":
                service_type = "company"
                is_doc = False
            elif is_media_or_doc is not None:
                is_doc = bool(is_media_or_doc)
                service_type = "media" if is_doc else "image"
            else:
                is_doc = ImageKitService.is_document_or_media(original_name, folder)
                service_type = "media" if is_doc else "image"

            ik = ImageKitService.get_instance(service_type)

            if not ik:
                logger.error(
                    f"ImageKit client ({service_type}) not available. Upload aborted."
                )
                return None

            # Read bytes
            if hasattr(file_obj, "read"):
                file_content = file_obj.read()
                if hasattr(file_obj, "seek"):
                    file_obj.seek(0)
            elif isinstance(file_obj, bytes):
                file_content = file_obj
            else:
                file_content = bytes(file_obj)

            # Convert convertible raster images to WebP (skip SVGs, GIFs, and non-images)
            convertible_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".jfif", ".avif"}
            if not is_doc and convert_to_webp and ext in convertible_extensions:
                converted_content, new_name = ImageKitService._convert_to_webp(
                    file_content
                )
                if converted_content is not None:
                    file_content = converted_content
                    original_name = os.path.splitext(original_name)[0] + ".webp"

            # Normalize folder path
            normalized_folder = folder.replace("\\", "/")
            if not normalized_folder.startswith("/"):
                normalized_folder = "/" + normalized_folder

            # Upload via SDK
            response = ik.files.upload(
                file=file_content,
                file_name=original_name,
                folder=normalized_folder,
                use_unique_file_name=True,
            )

            # SDK v5.x returns UploadResponse object
            if response and hasattr(response, "url"):
                logger.info(
                    f"ImageKit ({service_type}) upload success: {response.url} (file_id: {response.file_id})"
                )
                return {
                    "url": response.url,
                    "file_id": response.file_id,
                    "name": response.name,
                }

            if hasattr(response, "response_metadata"):
                logger.error(
                    f"ImageKit ({service_type}) upload error: {response.response_metadata}"
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
        Checks all 3 ImageKit endpoints and deletes matching file_id.
        """
        if not file_url:
            return False

        # Determine which client and endpoint matches
        ep1 = getattr(settings, "IMAGEKIT_URL_ENDPOINT", "").rstrip("/")
        ep2 = getattr(settings, "IMAGEKIT_URL_ENDPOINT2", "").rstrip("/")
        ep3 = getattr(settings, "IMAGEKIT_URL_ENDPOINT3", "").rstrip("/")

        if ep3 and file_url.startswith(ep3):
            service_type = "company"
            endpoint = ep3
            private_key = getattr(settings, "IMAGEKIT_PRIVATE_KEY3", "")
        elif ep2 and file_url.startswith(ep2):
            service_type = "media"
            endpoint = ep2
            private_key = getattr(settings, "IMAGEKIT_PRIVATE_KEY2", "") or getattr(
                settings, "IMAGEKIT_PRIVATE_KEY", ""
            )
        elif ep1 and file_url.startswith(ep1):
            service_type = "image"
            endpoint = ep1
            private_key = getattr(settings, "IMAGEKIT_PRIVATE_KEY", "")
        else:
            # Check by extension if URL is relative or custom domain
            is_img = ImageKitService.is_image(file_url)
            service_type = "image" if is_img else "media"
            endpoint = ep1 if is_img else ep2
            private_key = getattr(settings, "IMAGEKIT_PRIVATE_KEY" if is_img else "IMAGEKIT_PRIVATE_KEY2", "")

        ik = ImageKitService.get_instance(service_type)
        if not ik:
            return False

        try:
            path_val = file_url[len(endpoint) :].lstrip("/") if endpoint and file_url.startswith(endpoint) else file_url
            folder = os.path.dirname(path_val)
            if not folder.startswith("/"):
                folder = "/" + folder
            filename = os.path.basename(path_val)

            import httpx
            import time

            response = None
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    search_url = "https://api.imagekit.io/v1/files"
                    response = httpx.get(
                        search_url,
                        params={"name": filename, "path": folder},
                        auth=(private_key, ""),
                        timeout=5.0,
                    )
                    if response.status_code == 200:
                        break
                except httpx.RequestError as e:
                    if attempt == max_retries - 1:
                        raise e
                    time.sleep(2**attempt)

            if response and response.status_code == 200:
                file_list = response.json()
                for f in file_list:
                    if f.get("name") == filename and f.get("fileId"):
                        ik.files.delete(f["fileId"])
                        logger.info(f"ImageKit file deleted: {file_url}")
                        return True

        except Exception as e:
            logger.warning(f"ImageKit delete failed for {file_url}: {e}")

        return False

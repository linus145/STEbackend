import os
import logging
from io import BytesIO
from PIL import Image
from django.core.files.storage import Storage
from django.conf import settings
from django.core.files.base import ContentFile
from maincore.imagekit_utils import ImageKitService

logger = logging.getLogger(__name__)


class ImageKitStorage(Storage):
    """
    Custom Django Storage backend that uploads files directly to ImageKit CDN.
    Used as a drop-in replacement for local file storage on model FileFields/ImageFields.
    """

    def __init__(self):
        self.client = ImageKitService.get_instance()

    def _save(self, name, content):
        # Normalize path separators
        name = name.replace("\\", "/")

        # Determine if it's an image that needs conversion
        ext = os.path.splitext(name)[1].lower()
        image_extensions = [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".jfif", ".avif"]

        if ext in image_extensions:
            try:
                img = Image.open(content)

                # Handle transparency
                if img.mode in ("RGBA", "LA"):
                    pass
                elif img.mode != "RGB":
                    img = img.convert("RGB")

                buffer = BytesIO()
                img.save(buffer, format="WEBP", quality=80)
                buffer.seek(0)

                content = ContentFile(buffer.read())
                name = os.path.splitext(name)[0] + ".webp"
            except Exception as e:
                logger.warning(f"Storage WebP conversion failed: {e}")
                if hasattr(content, "seek"):
                    content.seek(0)

        folder = os.path.dirname(name)
        filename = os.path.basename(name)

        # Ensure we are at the start of the file
        content.seek(0)

        if not self.client:
            logger.error("ImageKit client unavailable. Cannot save file.")
            return name

        try:
            file_bytes = content.read()

            res = self.client.files.upload(
                file=file_bytes,
                file_name=filename,
                folder=folder if folder else "/",
                use_unique_file_name=True,
            )

            if hasattr(res, "url"):
                logger.info(f"Storage upload success: {res.url}")
                return res.url

            logger.error(f"Storage upload returned no URL: {res}")
        except Exception as e:
            logger.exception(f"Storage upload failed: {e}")

        return name

    def url(self, name):
        # If name is already a full URL, return it
        if name and name.startswith("http"):
            return name
        # Otherwise, prepend endpoint
        return f"{settings.IMAGEKIT_URL_ENDPOINT.rstrip('/')}/{name.lstrip('/')}"

    def exists(self, name):
        return False

    def get_available_name(self, name, max_length=None):
        return name

    def size(self, name):
        return 0

    def delete(self, name):
        if not name:
            return
        ImageKitService.delete_file(name)

import os
import logging
from urllib.request import urlopen, Request
from django.core.files.storage import Storage
from django.conf import settings
from django.core.files.base import ContentFile
from maincore.imagekit_utils import ImageKitService

logger = logging.getLogger(__name__)


class ImageKitStorage(Storage):
    """
    Custom Django Storage backend that uploads files directly to ImageKit CDN.
    Accurately routes:
      - All Images (.jpg, .png, .webp, .svg, .gif, .bmp, .ico, .tiff, etc.) -> Endpoint 1 (IMAGEKIT_URL_ENDPOINT)
      - All PDFs, Documents & Media (.pdf, .doc, .xlsx, .txt, .zip, etc.)  -> Endpoint 2 (IMAGEKIT_URL_ENDPOINT2)
    """

    def _save(self, name, content):
        # Normalize path separators
        name = name.replace("\\", "/")
        folder = os.path.dirname(name)
        filename = os.path.basename(name)

        is_img = ImageKitService.is_image(filename)
        is_doc = not is_img
        
        result = ImageKitService.upload_file(
            file_obj=content,
            folder=folder if folder else "/uploads",
            file_name=filename,
            convert_to_webp=is_img,
            is_media_or_doc=is_doc,
        )

        if result and "url" in result:
            logger.info(f"ImageKitStorage save succeeded: {result['url']}")
            return result["url"]

        logger.warning(f"ImageKitStorage upload returned no URL for {name}. Returning original name.")
        return name

    def url(self, name):
        if not name:
            return ""
        # If name is already a full URL, return it
        if name.startswith("http://") or name.startswith("https://"):
            return name

        filename = os.path.basename(name)
        is_img = ImageKitService.is_image(filename)

        endpoint = ImageKitService.get_endpoint("image" if is_img else "media")
        if not endpoint:
            endpoint = getattr(settings, "IMAGEKIT_URL_ENDPOINT", "")

        return f"{endpoint.rstrip('/')}/{name.lstrip('/')}"

    def _open(self, name, mode="rb"):
        """
        Allows reading remote files stored on ImageKit as Django File objects.
        """
        file_url = self.url(name)
        try:
            req = Request(file_url, headers={"User-Agent": "Django-ImageKit-Storage"})
            with urlopen(req, timeout=15) as resp:
                data = resp.read()
                return ContentFile(data, name=os.path.basename(name))
        except Exception as e:
            logger.error(f"ImageKitStorage _open failed for {file_url}: {e}")
            raise

    def exists(self, name):
        return False

    def get_available_name(self, name, max_length=None):
        return name

    def size(self, name):
        return 0

    def delete(self, name):
        if not name:
            return
        file_url = self.url(name)
        ImageKitService.delete_file(file_url)

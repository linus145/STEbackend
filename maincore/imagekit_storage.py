import os
from io import BytesIO
from PIL import Image
from django.core.files.storage import Storage
from django.conf import settings
from imagekitio import ImageKit
from django.core.files.base import ContentFile
from maincore.imagekit_utils import ImageKitService

class ImageKitStorage(Storage):
    def __init__(self):
        # Using the same singleton instance from our utils
        self.client = ImageKitService.get_instance()

    def _save(self, name, content):
        # Normalize path
        name = name.replace("\\", "/")

        # Determine if it's an image that needs conversion
        ext = os.path.splitext(name)[1].lower()
        image_extensions = [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".jfif", ".avif"]

        if ext in image_extensions:
            try:
                # Open image and convert to WebP
                img = Image.open(content)

                # Convert to RGB if needed
                if img.mode in ("RGBA", "LA"):
                    pass
                elif img.mode != "RGB":
                    img = img.convert("RGB")

                buffer = BytesIO()
                img.save(buffer, format="WEBP", quality=80)
                buffer.seek(0)

                # Update content and name
                content = ContentFile(buffer.read())
                name = os.path.splitext(name)[0] + ".webp"
            except Exception as e:
                # If conversion fails, proceed with original
                print(f"DEBUG: Storage conversion failed: {e}")
                if hasattr(content, "seek"):
                    content.seek(0)

        folder = os.path.dirname(name)
        filename = os.path.basename(name)

        # Ensure we are at the start of the file
        content.seek(0)

        # Upload to ImageKit
        res = self.client.files.upload(
            file=content.read(),
            file_name=filename,
            folder=folder if folder else "/",
            use_unique_file_name=True,
        )

        if hasattr(res, "url"):
            return res.url

        return name

    def url(self, name):
        # If name is already a full URL, return it
        if name.startswith("http"):
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

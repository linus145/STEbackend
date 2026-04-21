import os
from imagekitio import ImageKit
from django.conf import settings

class ImageKitService:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            if not all([
                settings.IMAGEKIT_PUBLIC_KEY,
                settings.IMAGEKIT_PRIVATE_KEY,
                settings.IMAGEKIT_URL_ENDPOINT
            ]):
                return None
                
            cls._instance = ImageKit(
                private_key=settings.IMAGEKIT_PRIVATE_KEY
            )
        return cls._instance

    @staticmethod
    def get_auth_params():
        ik = ImageKitService.get_instance()
        if not ik:
            return None
        return ik.helper.get_authentication_parameters()

    @staticmethod
    def delete_file(file_url):
        """
        Deletes a file from ImageKit given its full URL.
        """
        ik = ImageKitService.get_instance()
        if not ik or not file_url:
            return False

        try:
            # Extract path from URL
            endpoint = settings.IMAGEKIT_URL_ENDPOINT.rstrip('/')
            if not file_url.startswith(endpoint):
                return False
                
            path_val = file_url[len(endpoint):].lstrip('/')
            
            # For SDK 5.x, we search for the file to get its ID
            import os
            folder = os.path.dirname(path_val)
            if not folder.startswith('/'):
                folder = '/' + folder
            filename = os.path.basename(path_val)

            files = ik.files.list(name=filename, path=folder)
            
            for file in files:
                if file.name == filename and (
                    file.folder_path == folder or file.folder_path == folder.rstrip('/')
                ):
                    ik.files.delete(file.file_id)
                    return True
        except Exception as e:
            print(f"DEBUG: ImageKit delete failed for {file_url}: {e}")
        
        return False

    @staticmethod
    def convert_to_webp(content, quality=80):
        """
        Converts image content to WebP format using Pillow.
        Returns (converted_content, new_filename)
        """
        from io import BytesIO
        from PIL import Image
        from django.core.files.base import ContentFile

        try:
            img = Image.open(content)
            
            # Convert to RGB if needed
            if img.mode in ("RGBA", "LA"):
                pass
            elif img.mode != "RGB":
                img = img.convert("RGB")

            buffer = BytesIO()
            img.save(buffer, format="WEBP", quality=quality)
            buffer.seek(0)
            
            return ContentFile(buffer.read()), "image.webp"
        except Exception as e:
            print(f"DEBUG: WebP conversion failed: {e}")
            if hasattr(content, 'seek'):
                content.seek(0)
            return content, None

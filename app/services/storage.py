import cloudinary
import cloudinary.uploader
from app.config import get_settings

settings = get_settings()

# Parse and configure Cloudinary from CLOUDINARY_URL
if settings.CLOUDINARY_URL:
    cloudinary.config(cloudinary_url=settings.CLOUDINARY_URL)


def upload_image(image_bytes: bytes, folder: str = "receipts") -> dict:
    """Upload an image to Cloudinary and return url + public_id."""
    result = cloudinary.uploader.upload(
        image_bytes,
        folder=folder,
        resource_type="image",
        transformation=[
            {"quality": "auto", "fetch_format": "auto"},
        ],
    )
    return {
        "url": result.get("secure_url"),
        "public_id": result.get("public_id"),
    }


def delete_image(public_id: str) -> bool:
    """Delete an image from Cloudinary by its public_id."""
    try:
        result = cloudinary.uploader.destroy(public_id)
        return result.get("result") == "ok"
    except Exception:
        return False

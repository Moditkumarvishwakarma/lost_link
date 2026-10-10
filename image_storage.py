from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

PROJECT_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = PROJECT_DIR / "uploads"
MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_EXTENSIONS = {"JPEG": ".jpg", "PNG": ".png"}


def save_uploaded_image(image_bytes: bytes) -> str:
    if not image_bytes:
        raise ValueError("The uploaded image is empty.")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("Images must be 5 MB or smaller.")

    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image_format = image.format
            image.verify()
    except (UnidentifiedImageError, OSError) as error:
        raise ValueError("Upload a valid PNG or JPEG image.") from error

    extension = IMAGE_EXTENSIONS.get(image_format or "")
    if extension is None:
        raise ValueError("Only PNG and JPEG images are supported.")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{extension}"
    target = UPLOAD_DIR / filename
    target.write_bytes(image_bytes)
    return target.relative_to(PROJECT_DIR).as_posix()


def get_uploaded_image_path(relative_path: str) -> Path | None:
    if not relative_path:
        return None
    try:
        target = (PROJECT_DIR / relative_path).resolve()
        target.relative_to(UPLOAD_DIR.resolve())
    except (OSError, ValueError):
        return None
    return target if target.is_file() else None


def delete_uploaded_image(relative_path: str) -> None:
    image_path = get_uploaded_image_path(relative_path)
    if image_path is not None:
        image_path.unlink()

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, UnidentifiedImageError


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}


class UploadValidationError(ValueError):
    """An uploaded file is too large or is not a supported image."""


def validate_uploaded_image(data: bytes) -> str:
    if not data:
        raise UploadValidationError("上传图片为空")
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadValidationError("上传图片超过10MB限制")
    try:
        with Image.open(BytesIO(data)) as image:
            image_format = str(image.format or "").upper()
            image.verify()
    except (UnidentifiedImageError, OSError) as error:
        raise UploadValidationError("上传文件不是可读取的图片") from error
    extension = ALLOWED_FORMATS.get(image_format)
    if extension is None:
        raise UploadValidationError("只支持JPEG、PNG和WebP图片")
    return extension


def save_validated_upload(data: bytes, upload_dir: Path) -> tuple[str, Path]:
    extension = validate_uploaded_image(data)
    sample_id = f"custom_{uuid4().hex}"
    upload_dir.mkdir(parents=True, exist_ok=True)
    output_path = upload_dir / f"{sample_id}{extension}"
    output_path.write_bytes(data)
    return sample_id, output_path

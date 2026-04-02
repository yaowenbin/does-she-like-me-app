from __future__ import annotations

import io
from typing import Tuple

from PIL import Image, ImageOps


def _preprocess_for_ocr(img: Image.Image) -> Image.Image:
    # Normalize orientation (EXIF) if present.
    img = ImageOps.exif_transpose(img)
    img = img.convert("L")

    # Gentle contrast enhancement.
    img = ImageOps.autocontrast(img)

    # Downscale large images to reduce OCR time.
    max_width = 1600
    if img.width > max_width:
        scale = max_width / float(img.width)
        new_h = int(img.height * scale)
        img = img.resize((max_width, new_h))

    # Simple threshold to improve text separation on chat screenshots.
    # (Keep it conservative; aggressive thresholding can destroy thin characters.)
    img = img.point(lambda p: 255 if p > 180 else 0)
    return img


def ocr_image_bytes(image_bytes: bytes, *, lang: str = "chi_sim") -> Tuple[str, str]:
    """
    Offline OCR for user-owned screenshots.

    Returns:
      (raw_text, used_lang)
    """

    # Lazy import: pytesseract requires the runtime Tesseract binary.
    try:
        import pytesseract
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "缺少 OCR Python 依赖：请先 `pip install pytesseract pillow`。"
        ) from e

    img = Image.open(io.BytesIO(image_bytes))
    img = _preprocess_for_ocr(img)

    try:
        text = pytesseract.image_to_string(img, lang=lang)
        return text or "", lang
    except Exception as e:
        # If the OCR engine itself isn't installed, give a clear actionable message.
        if hasattr(pytesseract, "TesseractNotFoundError") and isinstance(
            e, pytesseract.TesseractNotFoundError
        ):
            raise RuntimeError(
                "找不到 Tesseract 可执行文件（tesseract.exe）。"
                "请先安装 Tesseract OCR（例如：Windows 可用 `choco install tesseract`），并确保 `tesseract` 已加入 PATH。"
            )

        # Fallback: if Chinese lang pack isn't available, try English.
        if lang != "eng":
            text = pytesseract.image_to_string(img, lang="eng")
            return text or "", "eng"
        raise


from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path
from typing import List, Tuple
import time

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


def _preprocess_for_easyocr(img: Image.Image) -> Image.Image:
    """
    EasyOCR（深度学习）对“二值化”不敏感，过强阈值可能反而毁字形。
    这里只做轻量化预处理：旋转归一 + 灰度对比增强。
    """
    img = ImageOps.exif_transpose(img)
    img = img.convert("L")
    img = ImageOps.autocontrast(img)
    return img


def _easyocr_lang_list(lang: str) -> List[str]:
    # easyocr 支持的语言 key 不是 chi_sim/chi_tra 这种 tesseract 体系
    l = (lang or "").lower()
    if l.startswith("chi") or l.startswith("zh") or "chi" in l or "zho" in l:
        return ["ch_sim"]
    return ["en"]


def _easyocr_model_hint(lang_list_key: str) -> str:
    """
    给用户一个“手动下载模型权重”的最小指引。
    EasyOCR 第一次运行会下载：检测(craft) + 识别(按语言)。
    """
    # detection: 默认 craft
    craft_zip_url = "https://github.com/JaidedAI/EasyOCR/releases/download/pre-v1.1.6/craft_mlt_25k.zip"
    craft_pth = "craft_mlt_25k.pth"

    # recognition: 按我们在 _easyocr_lang_list 里映射的语言 key
    if lang_list_key == "ch_sim":
        zh_zip_url = "https://github.com/JaidedAI/EasyOCR/releases/download/v1.3/zh_sim_g2.zip"
        zh_pth = "zh_sim_g2.pth"
        return (
            "你当前的 EasyOCR 失败点通常是“模型权重下载”。\n"
            "如果你的网络无法访问 GitHub，建议手动下载以下两个 zip，并确保解压后在缓存目录中存在对应 .pth 文件：\n"
            f"- 检测模型 craft：{craft_zip_url}\n"
            f"  解压后需要：{craft_pth}\n"
            f"- 识别模型（中文简体）zh_sim：{zh_zip_url}\n"
            f"  解压后需要：{zh_pth}\n"
        )

    # fallback: 只给 craft，避免误导
    return (
        "你当前的 EasyOCR 失败点通常是“模型权重下载”。\n"
        "如果你的网络无法访问 GitHub，至少需要手动下载检测模型：\n"
        f"- craft：{craft_zip_url}\n"
        f"  解压后需要：{craft_pth}\n"
        "识别模型会随语言变化；你可以把 easyocr 缓存目录发我，我再帮你对照缺哪些 .pth。"
    )

@lru_cache(maxsize=4)
def _get_easyocr_reader(lang_list_key: str):
    """
    Reader 初始化非常重（会加载模型），所以做一个进程内缓存。
    """
    try:
        import easyocr  # lazy import: 让缺依赖时还能给出可读错误
    except Exception as e:
        # 这类错误通常是 torch 的 DLL/运行库问题（如 WinError 1114）。
        raise RuntimeError(
            "EasyOCR 启动失败（底层依赖无法正常初始化）。"
            "\n请你在后端运行：`python -c \"import torch\"` 看是否报同样错误。"
            "\n常见修复："
            "\n1) 安装/修复 Microsoft Visual C++ 2015-2022 运行库（x64）。"
            "\n2) 卸载并重装 CPU 版 torch："
            "\n   `pip uninstall -y torch torchvision torchaudio`"
            "\n   `pip install --no-cache-dir --force-reinstall --index-url https://download.pytorch.org/whl/cpu torch torchvision`"
            f"\n补充错误：{str(e)}"
        ) from e

    gpu = False  # Windows 默认先走 CPU，保证“能跑起来”
    model_dir = Path(__file__).resolve().parents[1] / ".easyocr_models"
    model_dir.mkdir(parents=True, exist_ok=True)

    # Reader 初始化会加载/下载模型权重；在网络不稳时可能失败，所以做一次轻量重试。
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            return easyocr.Reader(
                lang_list_key.split(","),
                gpu=gpu,
                model_storage_directory=str(model_dir),
                download_enabled=True,
            )
        except Exception as e:
            last_err = e
            if attempt == 0:
                time.sleep(2)
                continue
            break

    raise RuntimeError(
        "EasyOCR 初始化失败：可能在下载模型权重时网络连接超时/被拦截。"
        "\n模型缓存目录："
        + str(model_dir)
        + "\n"
        + _easyocr_model_hint(lang_list_key)
        + "（重启后端后重试即可）"
        + f"\n补充错误：{str(last_err)}"
    )


def _ocr_image_bytes_easyocr(image: Image.Image, *, lang: str) -> str:
    """
    EasyOCR 离线图片识别（不依赖系统 tesseract.exe）。
    """
    # EasyOCR 内部通常会按 RGB/单通道都能处理，但我们统一成 RGB
    try:
        import numpy as np
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "缺少 easyocr 运行依赖：请先安装 `easyocr`（它会自动安装 numpy/torch 等）。"
        ) from e

    # preprocess: 不做硬阈值
    img = _preprocess_for_easyocr(image).convert("RGB")
    img_np = np.array(img)

    lang_list = _easyocr_lang_list(lang)
    lang_key = ",".join(lang_list)
    reader = _get_easyocr_reader(lang_key)

    # detail=0: 只返回文字
    texts = reader.readtext(img_np, detail=0, paragraph=True)
    return "\n".join([t.strip() for t in texts if t and str(t).strip()])  # type: ignore[arg-type]


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
        # 优先处理：缺少系统 tesseract.exe -> 尝试 EasyOCR 替代（纯本地）。
        if hasattr(pytesseract, "TesseractNotFoundError") and isinstance(
            e, pytesseract.TesseractNotFoundError
        ):
            try:
                easy_text = _ocr_image_bytes_easyocr(Image.open(io.BytesIO(image_bytes)), lang=lang)
                return easy_text, "easyocr"
            except RuntimeError as ee:
                # 没装 easyocr 的情况下也要给可读提示
                raise RuntimeError(
                    "找不到 Tesseract 可执行文件（tesseract.exe）。"
                    "你仍可用离线 EasyOCR 替代图片识别："
                    "1) 安装：`pip install easyocr`（会下载模型，CPU 可用）"
                    "2) 重启后端后再试。"
                    f"\n补充错误：{str(ee)}"
                ) from ee
            except Exception as ee:  # pragma: no cover
                raise RuntimeError(
                    "tesseract 缺失且 EasyOCR 也无法完成识别。"
                    f"补充错误：{str(ee)}"
                ) from ee

        # Fallback: if Chinese lang pack isn't available, try English.
        if lang != "eng":
            text = pytesseract.image_to_string(img, lang="eng")
            return text or "", "eng"
        raise


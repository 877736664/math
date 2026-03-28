"""图片生成服务，负责为动画生成贴题素材。"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from urllib import error, request
from urllib.parse import urlparse


logger = logging.getLogger(__name__)


def is_doubao_image_ready() -> bool:
    """检查豆包生图配置是否可用。"""

    return bool(_api_key() and _base_url() and _model())


def generate_animation_images(prompts: list[str], variation_seed: str) -> list[dict]:
    """根据提示词生成动画素材图。"""

    if not is_doubao_image_ready():
        return []

    images: list[dict] = []
    for index, prompt in enumerate(prompts[:3]):
        final_prompt = f"{prompt}\nVariation seed: {variation_seed}\nKeep the same educational scene."
        image_url = _get_or_create_cached_image(final_prompt, index)
        if not image_url:
            continue
        images.append(
            {
                "query": f"doubao-image-{index + 1}",
                "image_url": image_url,
                "source_page": "",
                "source_host": "Doubao Seedream",
            }
        )
    return images


def get_generated_image_path(file_name: str) -> Path:
    """校验并定位本地缓存的图片文件。"""

    safe_name = Path(file_name).name
    file_path = _cache_dir() / safe_name
    if not file_path.is_file():
        raise FileNotFoundError(safe_name)
    return file_path


def _get_or_create_cached_image(prompt: str, index: int) -> str:
    digest = hashlib.sha256(f"{_model()}|{_size()}|{prompt}".encode("utf-8")).hexdigest()[:24]
    file_stem = f"doubao_{index + 1}_{digest}"

    for existing in _cache_dir().glob(f"{file_stem}.*"):
        if existing.is_file() and existing.stat().st_size > 0:
            return _public_image_url(existing.name)

    remote_url = _generate_single_image(prompt)
    if not remote_url:
        return ""

    file_path = _download_image_to_cache(remote_url, file_stem)
    return _public_image_url(file_path.name) if file_path else ""


def _download_image_to_cache(remote_url: str, file_stem: str) -> Path | None:
    http_request = request.Request(remote_url, headers={"User-Agent": "Mozilla/5.0"}, method="GET")

    try:
        with request.urlopen(http_request, timeout=float(os.getenv("DOUBAO_IMAGE_DOWNLOAD_TIMEOUT", "90"))) as response:
            content_type = response.headers.get("Content-Type", "")
            payload = response.read()
    except Exception:
        logger.exception("Doubao image download failed")
        return None

    extension = _guess_extension(remote_url, content_type)
    file_path = _cache_dir() / f"{file_stem}{extension}"
    file_path.write_bytes(payload)
    return file_path


def _generate_single_image(prompt: str) -> str:
    payload = {
        "model": _model(),
        "prompt": prompt,
        "size": _size(),
    }
    http_request = request.Request(
        _base_url(),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_api_key()}",
        },
        method="POST",
    )

    try:
        with request.urlopen(http_request, timeout=float(os.getenv("DOUBAO_IMAGE_TIMEOUT", "120"))) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        logger.warning("Doubao image generation failed with HTTP %s: %s", exc.code, detail)
        return ""
    except Exception:
        logger.exception("Doubao image generation request failed")
        return ""

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Doubao image generation returned non-JSON response")
        return ""

    items = data.get("data", [])
    if not isinstance(items, list) or not items:
        return ""
    first = items[0] if isinstance(items[0], dict) else {}
    return str(first.get("url", "")).strip()


def _guess_extension(remote_url: str, content_type: str) -> str:
    lowered = content_type.lower()
    if "png" in lowered:
        return ".png"
    if "webp" in lowered:
        return ".webp"
    if "jpeg" in lowered or "jpg" in lowered:
        return ".jpg"

    suffix = Path(urlparse(remote_url).path).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    return ".jpg"


def _cache_dir() -> Path:
    cache_dir = Path(os.getenv("DOUBAO_IMAGE_CACHE_DIR", "./generated_assets/images"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _public_image_url(file_name: str) -> str:
    return f"{_public_base_url().rstrip('/')}/api/generated-images/{file_name}"


def _api_key() -> str:
    return os.getenv("DOUBAO_IMAGE_API_KEY", "").strip()


def _base_url() -> str:
    return os.getenv("DOUBAO_IMAGE_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3/images/generations").strip()


def _model() -> str:
    return os.getenv("DOUBAO_IMAGE_MODEL", "doubao-seedream-5-0-260128").strip()


def _size() -> str:
    return os.getenv("DOUBAO_IMAGE_SIZE", "1920x1920").strip()


def _public_base_url() -> str:
    return os.getenv("BACKEND_PUBLIC_BASE_URL", "http://127.0.0.1:8000").strip()

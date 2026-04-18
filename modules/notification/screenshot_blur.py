"""Screenshot capture + privacy blur with masked-card overlay (Blueprint §6 Ngã rẽ 2).

Requires Pillow; degrades gracefully (returns raw screenshot) if absent.
"""
from __future__ import annotations

import io
import logging
from typing import Optional

from modules.notification.card_masker import mask_card_number

_logger = logging.getLogger(__name__)


def _render(raw_png: bytes, masked: str) -> bytes:
    # pylint: disable=import-outside-toplevel
    from PIL import Image, ImageDraw, ImageFilter  # noqa: PLC0415
    img = Image.open(io.BytesIO(raw_png)).convert("RGBA")
    blurred = img.filter(ImageFilter.GaussianBlur(radius=2))
    draw = ImageDraw.Draw(blurred)
    try:
        bbox = draw.textbbox((0, 0), masked)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        tw, th = draw.textsize(masked)  # type: ignore[attr-defined]
    pad, margin = 6, 10
    x0 = blurred.size[0] - tw - pad * 2 - margin
    y0 = margin
    x1, y1 = blurred.size[0] - margin, y0 + th + pad * 2
    overlay = Image.new("RGBA", blurred.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rectangle([x0, y0, x1, y1], fill=(0, 0, 0, 180))
    composed = Image.alpha_composite(blurred, overlay)
    ImageDraw.Draw(composed).text((x0 + pad, y0 + pad), masked, fill=(255, 255, 255, 255))
    out = io.BytesIO()
    composed.convert("RGB").save(out, format="PNG")
    return out.getvalue()


def capture_and_blur(driver, card_number: str) -> Optional[bytes]:
    """Capture screenshot + overlay masked card. Raw PNG on Pillow miss; None on failure."""
    try:
        raw_png = driver.get_screenshot_as_png()
    except Exception as exc:  # noqa: BLE001
        _logger.warning("capture_and_blur: screenshot failed: %s", exc)
        return None
    try:
        return _render(raw_png, mask_card_number(card_number))
    except ImportError:
        _logger.warning("capture_and_blur: Pillow missing — returning raw screenshot.")
        return raw_png
    except Exception as exc:  # noqa: BLE001
        _logger.warning("capture_and_blur: image processing failed: %s", exc)
        return raw_png

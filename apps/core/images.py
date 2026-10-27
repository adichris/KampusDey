"""Upload hardening for photos: sniff, verify, strip EXIF, randomise name, perceptual hash."""

from __future__ import annotations

import io
import math
import uuid

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils.translation import gettext as _
from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF", "MPO"}
MAX_PIXELS = 40_000_000
MAX_EDGE = 2400


def clean_image(upload, max_mb: int) -> tuple[ContentFile, int, int, str]:
    """Return (file, width, height, phash) for a safe re-encoded copy of the upload.

    The image is re-encoded from pixels only, so EXIF (including GPS), ICC and any trailing
    payload is dropped. Orientation is applied first so photos are not rotated.
    """
    size = getattr(upload, "size", None) or 0
    if size > max_mb * 1024 * 1024:
        raise ValidationError(_("Photo is larger than %(mb)s MB.") % {"mb": max_mb})
    head = upload.read(16)
    upload.seek(0)
    if not _looks_like_image(head):
        raise ValidationError(_("That file is not a supported image."))
    try:
        probe = Image.open(upload)
        probe.verify()
        upload.seek(0)
        img = Image.open(upload)
        if img.format not in ALLOWED_FORMATS:
            raise ValidationError(_("Unsupported image format."))
        if img.width * img.height > MAX_PIXELS:
            raise ValidationError(_("Image dimensions are too large."))
        img.load()
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise ValidationError(_("That file is not a valid image.")) from exc
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "transparency" in img.info else "RGB")
    img.thumbnail((MAX_EDGE, MAX_EDGE))
    phash = perceptual_hash(img)
    out = io.BytesIO()
    clean = Image.new(img.mode, img.size)
    clean.paste(img)
    if clean.mode == "RGBA":
        clean.save(out, format="WEBP", quality=85)
        ext = "webp"
    else:
        clean.save(out, format="JPEG", quality=85, optimize=True, progressive=True)
        ext = "jpg"
    return (
        ContentFile(out.getvalue(), name=f"{uuid.uuid4().hex}.{ext}"),
        clean.width,
        clean.height,
        phash,
    )


def _looks_like_image(head: bytes) -> bool:
    return (
        head.startswith(b"\xff\xd8\xff")
        or head.startswith(b"\x89PNG\r\n\x1a\n")
        or head[:4] == b"RIFF"
        and head[8:12] == b"WEBP"
        or head[:6] in (b"GIF87a", b"GIF89a")
    )


def _dct_1d(vector: list[float]) -> list[float]:
    n = len(vector)
    return [
        sum(vector[x] * math.cos(math.pi * (x + 0.5) * k / n) for x in range(n)) for k in range(n)
    ]


def perceptual_hash(img: Image.Image, hash_size: int = 8, highfreq_factor: int = 4) -> str:
    """pHash (DCT based), compatible in spirit with `imagehash.phash`; 64-bit hex string."""
    size = hash_size * highfreq_factor
    gray = img.convert("L").resize((size, size), Image.Resampling.LANCZOS)
    pixels = list(gray.getdata())
    rows = [_dct_1d([float(p) for p in pixels[r * size : (r + 1) * size]]) for r in range(size)]
    cols = [_dct_1d([rows[r][c] for r in range(size)]) for c in range(hash_size)]
    low = [cols[c][r] for r in range(hash_size) for c in range(hash_size)]
    median = sorted(low)[len(low) // 2]
    bits = "".join("1" if v > median else "0" for v in low)
    return f"{int(bits, 2):016x}"


def hamming(a: str | None, b: str | None) -> int:
    if not a or not b:
        return 64
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def has_exif(data: bytes) -> bool:
    img = Image.open(io.BytesIO(data))
    return bool(img.getexif()) or "exif" in img.info

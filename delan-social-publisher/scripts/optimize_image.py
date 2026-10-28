#!/usr/bin/env python3
"""Crop, strip metadata from, compress, and validate a Delan social WebP image."""

from __future__ import annotations

import argparse
import io
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageOps


TARGETS = {
    "social": {"ratio": 1.0, "max_size": (1600, 1600), "min_size": (960, 960), "max_bytes": 750 * 1024},
}
PIXEL_CHUNKS = {b'VP8 ', b'VP8L', b'VP8X', b'ALPH'}
TRANSPORT_MAX_BYTES = 750 * 1024


def flatten_to_rgb(image: Image.Image) -> Image.Image:
    if image.mode == "RGB":
        return image.copy()
    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, "white")
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return image.convert("RGB")


def crop_to_ratio(image: Image.Image, ratio: float) -> Image.Image:
    width, height = image.size
    current = width / height
    if math.isclose(current, ratio, rel_tol=0.002):
        return image
    if current > ratio:
        crop_width = max(1, round(height * ratio))
        left = (width - crop_width) // 2
        return image.crop((left, 0, left + crop_width, height))
    crop_height = max(1, round(width / ratio))
    top = (height - crop_height) // 2
    return image.crop((0, top, width, top + crop_height))


def downscale(image: Image.Image, max_size: tuple[int, int]) -> Image.Image:
    if image.width <= max_size[0] and image.height <= max_size[1]:
        return image
    result = image.copy()
    result.thumbnail(max_size, Image.Resampling.LANCZOS)
    return result


def strip_metadata(image: Image.Image) -> Image.Image:
    """Rebuild from pixels so EXIF, XMP, ICC and source container data cannot survive."""
    rgb = flatten_to_rgb(image)
    return Image.frombytes("RGB", rgb.size, rgb.tobytes())


def encode_webp(image: Image.Image, quality: int) -> bytes:
    buffer = io.BytesIO()
    image.save(
        buffer,
        format="WEBP",
        quality=quality,
        method=6,
        lossless=False,
    )
    return buffer.getvalue()


def encode_jpeg(image: Image.Image, quality: int) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True, progressive=True, subsampling="4:2:0")
    return buffer.getvalue()


def create_transport_jpeg(image: Image.Image, path: Path) -> dict[str, object]:
    for quality in range(90, 71, -2):
        encoded = encode_jpeg(image, quality)
        if len(encoded) <= TRANSPORT_MAX_BYTES:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(encoded)
            result = validate_transport(path, image.size)
            return dict(result, quality=quality)
    raise RuntimeError("Unable to create the temporary social-upload JPEG below 750 KiB")


def compress(image: Image.Image, max_bytes: int, min_size: tuple[int, int]) -> tuple[bytes, Image.Image, int]:
    working = image
    while True:
        for quality in range(88, 67, -2):
            encoded = encode_webp(working, quality)
            if len(encoded) <= max_bytes:
                return encoded, working, quality
        if working.width <= min_size[0] or working.height <= min_size[1]:
            break
        next_size = (max(min_size[0], round(working.width * 0.9)), max(min_size[1], round(working.height * 0.9)))
        if next_size == working.size:
            break
        working = working.resize(next_size, Image.Resampling.LANCZOS)
    raise RuntimeError(f"Unable to compress image below {max_bytes} bytes at WebP quality >= 68 without shrinking below {min_size[0]}x{min_size[1]}")


def metadata_chunks(data: bytes) -> list[str]:
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise RuntimeError('Invalid WebP container')
    if int.from_bytes(data[4:8], 'little') + 8 != len(data):
        raise RuntimeError('Invalid WebP container length or trailing data')
    chunks: list[str] = []
    offset = 12
    while offset + 8 <= len(data):
        name = data[offset : offset + 4]
        size = int.from_bytes(data[offset + 4 : offset + 8], "little")
        if offset + 8 + size + size % 2 > len(data):
            raise RuntimeError('Truncated WebP chunk')
        if name not in PIXEL_CHUNKS:
            chunks.append(name.decode("ascii", errors='replace').strip())
        offset += 8 + size + (size % 2)
    if offset != len(data):
        raise RuntimeError('Trailing WebP container bytes')
    return chunks


def jpeg_metadata(data):
    """Check all segments, including segments between progressive scans; keep only JFIF APP0."""
    if not data.startswith(b'\xff\xd8'):
        raise RuntimeError('Invalid JPEG container')
    found, pos = [], 2
    while pos < len(data):
        if data[pos] != 255:  # Entropy-coded scan byte.
            pos += 1
            continue
        while pos < len(data) and data[pos] == 255:
            pos += 1
        if pos == len(data):
            break
        marker = data[pos]
        pos += 1
        if marker == 0 or 208 <= marker <= 215:
            continue
        if marker == 217:
            if pos != len(data):
                found.append('trailing-data')
            return found
        if pos + 2 > len(data):
            break
        length = int.from_bytes(data[pos:pos+2], 'big')
        if length < 2 or pos + length > len(data):
            raise RuntimeError('Truncated JPEG segment')
        if 225 <= marker <= 239 or marker == 254 or (marker == 224 and (length != 16 or data[pos+2:pos+7] != b'JFIF\0')):
            found.append(f'APP{marker-224}' if 224 <= marker <= 239 else 'COMMENT')
        pos += length
    raise RuntimeError('JPEG missing end marker')


def validate_transport(path, dimensions=None):
    path = Path(path)
    if path.stat().st_size > TRANSPORT_MAX_BYTES:
        raise RuntimeError('Transport exceeds 750 KiB')
    with Image.open(path) as im:
        im.verify()
    with Image.open(path) as im:
        if im.format != 'JPEG' or (dimensions and im.size != dimensions):
            raise RuntimeError('Transport must be JPEG with canonical image dimensions')
        if im.getexif() or any(k in im.info for k in ('exif', 'xmp', 'icc_profile', 'comment')):
            raise RuntimeError('Transport contains metadata')
        width, height = im.size
    markers = jpeg_metadata(path.read_bytes())
    if markers:
        raise RuntimeError('Transport contains non-pixel metadata: ' + ', '.join(markers))
    return {'path': str(path), 'format': 'JPEG', 'width': width, 'height': height,
            'bytes': path.stat().st_size, 'metadata_removed': True, 'metadata_segments': markers}


def validate(path: Path, kind: str, max_bytes: int) -> dict[str, object]:
    if path.suffix.lower() != ".webp":
        raise RuntimeError("Output path must use the .webp extension")
    size = path.stat().st_size
    if size > max_bytes:
        raise RuntimeError(f"Output is {size} bytes, above the {max_bytes}-byte limit")
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        if image.format != "WEBP":
            raise RuntimeError(f"Output format is {image.format}, expected WEBP")
        width, height = image.size
    embedded_metadata = metadata_chunks(path.read_bytes())
    if embedded_metadata:
        raise RuntimeError(f"Output still contains metadata chunks: {', '.join(embedded_metadata)}")
    minimum = TARGETS[kind]["min_size"]
    maximum = TARGETS[kind]["max_size"]
    if width < minimum[0] or height < minimum[1] or width > maximum[0] or height > maximum[1]:
        raise RuntimeError("Social image must be between 960x960 and 1600x1600")
    ratio = width / height
    expected = TARGETS[kind]["ratio"]
    if abs(ratio - expected) > 0.01:
        raise RuntimeError(f"Output ratio {ratio:.4f} does not match {expected:.4f}")
    return {
        "path": str(path),
        "kind": kind,
        "format": "WEBP",
        "width": width,
        "height": height,
        "bytes": size,
        "max_bytes": max_bytes,
        "metadata_removed": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--kind", choices=sorted(TARGETS), required=True)
    parser.add_argument("--max-bytes", type=int, help="Override the clarity-preserving per-kind byte ceiling")
    parser.add_argument("--transport-jpeg", type=Path, help="For social images only, create a temporary metadata-free desktop upload derivative")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target = TARGETS[args.kind]
    max_bytes = args.max_bytes or target["max_bytes"]
    if max_bytes <= 0:
        raise ValueError("--max-bytes must be positive")
    if not args.input.is_file():
        raise FileNotFoundError(args.input)
    paths = [args.input.resolve(), args.output.resolve()]
    if args.transport_jpeg:
        paths.append(args.transport_jpeg.resolve())
    if len(paths) != len(set(paths)):
        raise ValueError('Source, canonical image and upload derivative must use distinct paths')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.transport_jpeg and args.kind != "social":
        raise ValueError("--transport-jpeg is valid only with --kind social")

    with Image.open(args.input) as source:
        source = ImageOps.exif_transpose(source)
        image = strip_metadata(source)
    image = crop_to_ratio(image, target["ratio"])
    if image.width < target["min_size"][0] or image.height < target["min_size"][1]:
        raise ValueError("Source is below the minimum social dimensions after cropping; do not upscale")
    image = downscale(image, target["max_size"])
    encoded, final_image, quality = compress(image, max_bytes, target["min_size"])
    args.output.write_bytes(encoded)

    result = validate(args.output, args.kind, max_bytes)
    result["quality"] = quality
    result["input"] = str(args.input)
    result["cropped_size"] = list(final_image.size)
    if args.transport_jpeg:
        result["transport_jpeg"] = create_transport_jpeg(final_image, args.transport_jpeg)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)

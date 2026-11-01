#!/usr/bin/env python3
"""
Simple experimental "mostly-black neutrals + tertiary reduction" GCR tool.

Approximates the style of separation used in tools like Alwan ColorHub's
Dynamic Maximum Black / strong GCR:

- In chromatic areas, reduce the tertiary (gray-producing) channel and
  replace it with black while trying to keep the visual cast.
- In neutrals/grays, push most of the build into black, leaving a small
  residual CMY for richness (so grays don't look flat or lifeless).
- Black start and residual controls let you tune aggressiveness.

This is a simple pixel-based approximation for experimentation.
It is NOT a full ICC DeviceLink or spectral model, and it does not match
commercial tools in quality or intelligence. Best results come from files
that are already in a GRACoL-like (or similar) CMYK space.

Supports:
  - Raster: TIFF (CMYK preferred), JPEG, PNG, etc.
  - PDF: rasterizes pages, processes them, writes multi-page TIFF or PDF.

Dependencies: Pillow, numpy, pdf2image (and poppler for PDF).

Usage examples:
  python gcr_tool.py input.tif -o output.tif --strength 0.7 --black-start 0.05 --residual 0.15
  python gcr_tool.py input.pdf -o output.tif --strength 0.8 --residual 0.1
  python gcr_tool.py input.pdf -o output.pdf --strength 0.6 --dpi 150
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

try:
    from pdf2image import convert_from_path, pdfinfo_from_path
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False


def apply_gcr(cmyk, strength=0.7, black_start=0.0, residual=0.15, max_black=1.0):
    """
    Apply a controllable GCR-style transform to a CMYK array (values 0-1).

    Parameters
    ----------
    cmyk : ndarray, shape (H, W, 4), float32, range 0-1
    strength : float 0-1
        How much of the eligible gray component to replace with black.
        0 = no change, 1 = maximum replacement (subject to residual).
    black_start : float 0-1
        Gray component below this value is left alone (protects highlights).
    residual : float 0-1
        Fraction of the gray component left as CMY for richness in neutrals.
        Lower = more pure black, higher = more residual CMY.
    max_black : float 0-1
        Cap on the black channel.

    Returns
    -------
    ndarray of same shape, values clipped to 0-1
    """
    c, m, y, k = cmyk[..., 0], cmyk[..., 1], cmyk[..., 2], cmyk[..., 3]

    # Gray component = minimum of the three chromatic channels
    gray = np.minimum(np.minimum(c, m), y)

    # Eligible gray for replacement (above black_start)
    eligible = np.maximum(gray - black_start, 0.0)

    # Amount of gray we will actually replace
    # residual keeps some CMY for richness
    replaceable = eligible * strength * (1.0 - residual)
    replaceable = np.clip(replaceable, 0.0, None)

    # New chromatic channels (subtract the replaced amount)
    c_new = np.maximum(c - replaceable, 0.0)
    m_new = np.maximum(m - replaceable, 0.0)
    y_new = np.maximum(y - replaceable, 0.0)

    # New black = original black + the amount we replaced
    k_new = k + replaceable
    k_new = np.minimum(k_new, max_black)

    out = np.stack([c_new, m_new, y_new, k_new], axis=-1)
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def process_image(img, strength, black_start, residual, max_black):
    """Process a PIL Image. Converts to CMYK if needed, applies GCR, returns CMYK Image."""
    # Ensure we have a CMYK image
    if img.mode != "CMYK":
        # Convert via RGB for non-CMYK inputs (lossy for color accuracy)
        img = img.convert("CMYK")

    arr = np.array(img, dtype=np.float32) / 255.0
    arr = apply_gcr(arr, strength=strength, black_start=black_start,
                    residual=residual, max_black=max_black)
    arr = (arr * 255.0).astype(np.uint8)
    return Image.fromarray(arr, mode="CMYK")


def process_raster(input_path, output_path, strength, black_start, residual, max_black):
    img = Image.open(input_path)
    out = process_image(img, strength, black_start, residual, max_black)
    # Prefer TIFF for CMYK
    out.save(output_path, format="TIFF", compression="tiff_lzw")
    print(f"Saved: {output_path}")


def process_pdf(input_path, output_path, strength, black_start, residual, max_black, dpi=150, out_format="tiff"):
    if not PDF2IMAGE_AVAILABLE:
        raise RuntimeError("pdf2image is required for PDF support. Install with: pip install pdf2image")

    print(f"Rasterizing PDF at {dpi} DPI...")
    pages = convert_from_path(input_path, dpi=dpi)

    processed = []
    for i, page in enumerate(pages):
        print(f"  Processing page {i+1}/{len(pages)}")
        processed.append(process_image(page, strength, black_start, residual, max_black))

    out_path = Path(output_path)
    if out_format.lower() == "pdf" or out_path.suffix.lower() == ".pdf":
        # Save as multi-page PDF (RGB conversion under the hood for PDF)
        # Note: PDF from PIL is RGB; for true CMYK PDF you'd need a different toolchain.
        rgb_pages = [p.convert("RGB") for p in processed]
        rgb_pages[0].save(
            output_path,
            save_all=True,
            append_images=rgb_pages[1:],
            resolution=dpi,
            quality=95,
        )
        print(f"Saved multi-page PDF (RGB): {output_path}")
        print("Note: PDF output is RGB. For CMYK, use .tif output and place in a CMYK workflow.")
    else:
        # Multi-page TIFF (preserves CMYK)
        processed[0].save(
            output_path,
            save_all=True,
            append_images=processed[1:],
            compression="tiff_lzw",
        )
        print(f"Saved multi-page CMYK TIFF: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Experimental GCR tool: mostly-black neutrals + tertiary reduction"
    )
    parser.add_argument("input", help="Input file (TIFF/JPEG/PNG or PDF)")
    parser.add_argument("-o", "--output", required=True, help="Output file (.tif or .pdf)")
    parser.add_argument("--strength", type=float, default=0.7,
                        help="GCR strength 0.0-1.0 (default 0.7). Higher = more black replacement.")
    parser.add_argument("--black-start", type=float, default=0.02,
                        help="Black start threshold 0.0-1.0 (default 0.02). Protects light highlights.")
    parser.add_argument("--residual", type=float, default=0.15,
                        help="Residual CMY fraction 0.0-1.0 (default 0.15). "
                             "Lower = purer black grays, higher = richer residual CMY.")
    parser.add_argument("--max-black", type=float, default=1.0,
                        help="Maximum black channel 0.0-1.0 (default 1.0).")
    parser.add_argument("--dpi", type=int, default=150,
                        help="DPI for PDF rasterization (default 150).")
    args = parser.parse_args()

    # Clamp parameters
    strength = max(0.0, min(1.0, args.strength))
    black_start = max(0.0, min(1.0, args.black_start))
    residual = max(0.0, min(1.0, args.residual))
    max_black = max(0.0, min(1.0, args.max_black))

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    suffix = input_path.suffix.lower()
    is_pdf = suffix == ".pdf"

    print(f"Input:      {input_path}")
    print(f"Strength:   {strength:.2f}")
    print(f"Black start:{black_start:.2f}")
    print(f"Residual:   {residual:.2f}")
    print(f"Max black:  {max_black:.2f}")

    if is_pdf:
        process_pdf(
            str(input_path), args.output,
            strength, black_start, residual, max_black,
            dpi=args.dpi
        )
    else:
        process_raster(
            str(input_path), args.output,
            strength, black_start, residual, max_black
        )


if __name__ == "__main__":
    main()

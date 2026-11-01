# GCR Tool

**Gray Component Replacement** — a simple drag-and-drop browser tool for CMYK color separation tuning.

Replaces gray-producing CMY with black ink:
- **Neutrals/grays** → pushed mostly into black, with a small residual CMY for richness
- **Chromatic areas** → tertiary (gray-producing) channel reduced and replaced with black

## Usage

Double-click `app.py` (or run `python app.py`) and your browser opens to `http://localhost:5050`.

Drag & drop a **TIFF**, **JPEG**, **PNG**, or **PDF** and adjust the sliders:

| Control | Default | What it does |
|---------|---------|--------------|
| **Strength** | 0.70 | How aggressively gray component is replaced with black (0 = none, 1 = max) |
| **Black Start** | 0.02 | Gray component below this threshold is left alone (protects highlights) |
| **Residual** | 0.15 | Fraction of gray component kept as CMY for richness (lower = purer black) |
| **Max Black** | 1.00 | Cap on the black channel |

PDF inputs also get **DPI** and **output format** (TIFF for CMYK, PDF for RGB) options.

## Requirements

```
pip install flask numpy pillow
pip install pdf2image  # optional, for PDF support (requires Poppler)
```

## Notes

- This is a pixel-based approximation for experimentation, not a full ICC DeviceLink or spectral model
- Best results come from files already in a GRACoL-like CMYK space
- PDF output converts to RGB (Pillow limitation) — use TIFF output to preserve CMYK
- CLI version also available: `python gcr_tool.py input.tif -o output.tif --strength 0.7`

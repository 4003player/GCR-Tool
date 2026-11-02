#!/usr/bin/env python3
"""
GCR Tool — Fly.io server
Processes raster images and PDFs with Gray Component Replacement, returns CMYK TIFF.
"""

import os
import sys
import tempfile
from pathlib import Path

from flask import Flask, request, send_file, jsonify

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gcr_tool import process_image

try:
    from pdf2image import convert_from_path
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False

from PIL import Image

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200 MB


# ── CORS ──
ALLOWED_ORIGINS = [
    'https://4003player.github.io',
    'http://localhost',
    'http://127.0.0.1',
    'null',
]

@app.after_request
def add_cors(resp):
    origin = request.headers.get('Origin', '')
    if not origin or any(origin.startswith(o) for o in ALLOWED_ORIGINS):
        resp.headers['Access-Control-Allow-Origin'] = origin or '*'
        resp.headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
        resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        resp.headers['Access-Control-Max-Age'] = '86400'
    return resp


@app.route('/health')
def health():
    return jsonify(status='ok', pdf_support=PDF2IMAGE_AVAILABLE)


@app.route('/')
def index():
    return '''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>GCR Tool Server</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{background:#1a1a2e;color:#eee;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center}.card{max-width:480px;padding:48px 40px;text-align:center}h1{font-size:24px;margin-bottom:8px}.accent{color:#e94560}.sub{color:#999;font-size:14px;margin-bottom:32px}.status{display:inline-block;padding:6px 16px;border-radius:20px;font-size:13px;background:rgba(74,222,128,.15);color:#4ade80;margin-bottom:24px}.ep{background:#242424;border:1px solid #333;border-radius:10px;padding:20px;text-align:left;margin-bottom:20px}.ep code{font-family:'SF Mono',Consolas,monospace;font-size:13px;color:#e94560}.ep p{font-size:12px;color:#999;margin-top:4px}.footer{font-size:12px;color:#555}.footer a{color:#e94560;text-decoration:none}</style></head>
<body><div class="card">
<h1>🎨 <span class="accent">GCR Tool Server</span></h1>
<p class="sub">Gray Component Replacement — CMYK processing backend</p>
<div class="status">✓ Online</div>
<div class="ep">
<code>POST /process</code>
<p>Upload raster or PDF → get back CMYK TIFF with GCR applied</p>
<p style="margin-top:8px">Params: strength, black_start, residual, max_black, dpi, out_format</p>
</div>
<p class="footer">Backend for <a href="https://4003player.github.io/GCR-Tool/">GCR Tool</a> · © Mad Rtist Graphics</p>
</div></body></html>'''


@app.route('/process', methods=['POST', 'OPTIONS'])
def process():
    if request.method == 'OPTIONS':
        return '', 204

    f = request.files.get('file')
    if not f:
        return jsonify(error='No file uploaded'), 400

    strength    = float(request.form.get('strength', 0.7))
    black_start = float(request.form.get('black_start', 0.02))
    residual    = float(request.form.get('residual', 0.15))
    max_black   = float(request.form.get('max_black', 1.0))
    dpi         = int(request.form.get('dpi', 150))

    suffix = Path(f.filename).suffix.lower()
    is_pdf = suffix == '.pdf'
    base   = Path(f.filename).stem

    tmp_dir = tempfile.mkdtemp(prefix='gcr_')
    in_path = os.path.join(tmp_dir, f.filename)
    f.save(in_path)

    try:
        if is_pdf:
            if not PDF2IMAGE_AVAILABLE:
                return jsonify(error='PDF support not available on this server'), 400

            pages = convert_from_path(in_path, dpi=dpi)
            processed = []
            for page in pages:
                processed.append(process_image(page, strength, black_start, residual, max_black))

            out_path = os.path.join(tmp_dir, base + '_gcr.tif')
            processed[0].save(out_path, save_all=True, append_images=processed[1:],
                              compression='tiff_lzw')
            mime = 'image/tiff'
        else:
            img = Image.open(in_path)
            out_img = process_image(img, strength, black_start, residual, max_black)
            out_path = os.path.join(tmp_dir, base + '_gcr.tif')
            out_img.save(out_path, format='TIFF', compression='tiff_lzw')
            mime = 'image/tiff'

        return send_file(out_path, mimetype=mime, as_attachment=True,
                         download_name=os.path.basename(out_path))

    except Exception as e:
        return jsonify(error=str(e)), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print(f'\n  GCR Tool Server running on port {port}\n')
    app.run(host='0.0.0.0', port=port, debug=False)

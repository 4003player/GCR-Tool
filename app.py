#!/usr/bin/env python3
"""
GCR Tool – local web UI
Double-click to launch, then open http://localhost:5050 in your browser.
Drag & drop rasters (TIFF/JPEG/PNG) or PDFs, adjust sliders, download result.
"""

import os
import sys
import tempfile
import webbrowser
import threading
from pathlib import Path

from flask import Flask, request, send_file, jsonify, render_template_string

# Import the GCR processing functions from the co-located script
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gcr_tool import process_image, apply_gcr

try:
    from pdf2image import convert_from_path
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False

import numpy as np
from PIL import Image

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200 MB

HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GCR Tool</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg: #1a1a2e;
    --surface: #16213e;
    --card: #0f3460;
    --accent: #e94560;
    --accent-glow: rgba(233, 69, 96, .35);
    --text: #eee;
    --muted: #8899aa;
    --border: #2a3a5e;
    --radius: 10px;
  }

  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 30px 20px;
  }

  h1 {
    font-size: 1.8rem;
    font-weight: 700;
    margin-bottom: 4px;
    letter-spacing: -0.5px;
  }
  .subtitle {
    color: var(--muted);
    font-size: .85rem;
    margin-bottom: 28px;
  }

  .container {
    width: 100%;
    max-width: 640px;
    display: flex;
    flex-direction: column;
    gap: 18px;
  }

  /* ---- Drop Zone ---- */
  .drop-zone {
    border: 2px dashed var(--border);
    border-radius: var(--radius);
    background: var(--surface);
    padding: 44px 20px;
    text-align: center;
    cursor: pointer;
    transition: border-color .2s, background .2s, box-shadow .2s;
    position: relative;
  }
  .drop-zone.hover {
    border-color: var(--accent);
    background: rgba(233, 69, 96, .07);
    box-shadow: 0 0 20px var(--accent-glow);
  }
  .drop-zone.has-file {
    border-color: #3a9d5e;
    background: rgba(58, 157, 94, .08);
  }
  .drop-zone input { display: none; }
  .drop-icon { font-size: 2.4rem; margin-bottom: 8px; }
  .drop-label { font-size: .95rem; }
  .drop-file-name {
    margin-top: 8px;
    font-weight: 600;
    color: #5ec87a;
    font-size: .9rem;
    word-break: break-all;
  }

  /* ---- Controls ---- */
  .controls {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px 22px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }
  .control-row {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .control-row label {
    width: 110px;
    flex-shrink: 0;
    font-size: .82rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: .5px;
    color: var(--muted);
  }
  .control-row input[type=range] {
    flex: 1;
    accent-color: var(--accent);
    height: 6px;
  }
  .control-row .val {
    width: 48px;
    text-align: right;
    font-family: 'SF Mono', Consolas, monospace;
    font-size: .85rem;
    color: var(--text);
  }

  .control-row select {
    flex: 1;
    background: var(--card);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 6px 10px;
    font-size: .85rem;
  }

  /* ---- Button ---- */
  .process-btn {
    background: var(--accent);
    color: #fff;
    font-size: 1rem;
    font-weight: 700;
    border: none;
    border-radius: var(--radius);
    padding: 14px;
    cursor: pointer;
    transition: opacity .2s, box-shadow .2s;
    text-transform: uppercase;
    letter-spacing: 1px;
  }
  .process-btn:hover:not(:disabled) {
    opacity: .9;
    box-shadow: 0 0 18px var(--accent-glow);
  }
  .process-btn:disabled {
    opacity: .4;
    cursor: not-allowed;
  }

  /* ---- Progress ---- */
  .progress-wrap {
    display: none;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px 22px;
    text-align: center;
  }
  .progress-wrap.visible { display: block; }
  .progress-bar-track {
    width: 100%;
    height: 6px;
    background: var(--card);
    border-radius: 3px;
    overflow: hidden;
    margin-top: 10px;
  }
  .progress-bar {
    height: 100%;
    background: var(--accent);
    width: 0%;
    border-radius: 3px;
    transition: width .3s;
  }
  .progress-text {
    font-size: .82rem;
    color: var(--muted);
  }

  /* ---- Info ---- */
  .info {
    font-size: .75rem;
    color: var(--muted);
    text-align: center;
    line-height: 1.5;
    margin-top: 6px;
  }
</style>
</head>
<body>

<h1>GCR Tool</h1>
<p class="subtitle">Gray Component Replacement — drag &amp; drop rasters or PDFs</p>

<div class="container">

  <!-- Drop Zone -->
  <div class="drop-zone" id="dropZone">
    <input type="file" id="fileInput" accept=".tif,.tiff,.jpg,.jpeg,.png,.bmp,.pdf">
    <div class="drop-icon">📁</div>
    <div class="drop-label">Drop a file here or click to browse</div>
    <div class="drop-label" style="font-size:.78rem; color:var(--muted); margin-top:4px;">
      TIFF · JPEG · PNG · PDF
    </div>
    <div class="drop-file-name" id="fileName"></div>
  </div>

  <!-- Controls -->
  <div class="controls">
    <div class="control-row">
      <label>Strength</label>
      <input type="range" id="strength" min="0" max="100" value="70">
      <span class="val" id="strengthVal">0.70</span>
    </div>
    <div class="control-row">
      <label>Black Start</label>
      <input type="range" id="blackStart" min="0" max="100" value="2">
      <span class="val" id="blackStartVal">0.02</span>
    </div>
    <div class="control-row">
      <label>Residual</label>
      <input type="range" id="residual" min="0" max="100" value="15">
      <span class="val" id="residualVal">0.15</span>
    </div>
    <div class="control-row">
      <label>Max Black</label>
      <input type="range" id="maxBlack" min="0" max="100" value="100">
      <span class="val" id="maxBlackVal">1.00</span>
    </div>
    <div class="control-row" id="dpiRow" style="display:none;">
      <label>PDF DPI</label>
      <select id="dpi">
        <option value="72">72</option>
        <option value="150" selected>150</option>
        <option value="300">300</option>
      </select>
    </div>
    <div class="control-row" id="formatRow" style="display:none;">
      <label>Output</label>
      <select id="outFormat">
        <option value="tiff" selected>TIFF (CMYK)</option>
        <option value="pdf">PDF (RGB)</option>
      </select>
    </div>
  </div>

  <!-- Button -->
  <button class="process-btn" id="processBtn" disabled>Process</button>

  <!-- Progress -->
  <div class="progress-wrap" id="progressWrap">
    <div class="progress-text" id="progressText">Processing…</div>
    <div class="progress-bar-track"><div class="progress-bar" id="progressBar"></div></div>
  </div>

  <div class="info">
    Neutrals → mostly black &nbsp;·&nbsp; Chromatic → tertiary reduction<br>
    Output preserves CMYK via TIFF &nbsp;·&nbsp; PDF output converts to RGB
  </div>
</div>

<script>
const dropZone  = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const fileName  = document.getElementById('fileName');
const processBtn= document.getElementById('processBtn');
const dpiRow    = document.getElementById('dpiRow');
const formatRow = document.getElementById('formatRow');
const progressWrap = document.getElementById('progressWrap');
const progressBar  = document.getElementById('progressBar');
const progressText = document.getElementById('progressText');

let currentFile = null;

// Slider wiring
['strength','blackStart','residual','maxBlack'].forEach(id => {
  const slider = document.getElementById(id);
  const valEl  = document.getElementById(id + 'Val');
  const update = () => { valEl.textContent = (slider.value / 100).toFixed(2); };
  slider.addEventListener('input', update);
  update();
});

// Drop zone
dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('hover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('hover'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('hover');
  if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', () => { if (fileInput.files.length) setFile(fileInput.files[0]); });

function setFile(file) {
  currentFile = file;
  fileName.textContent = file.name;
  dropZone.classList.add('has-file');
  processBtn.disabled = false;

  const isPdf = file.name.toLowerCase().endsWith('.pdf');
  dpiRow.style.display    = isPdf ? 'flex' : 'none';
  formatRow.style.display = isPdf ? 'flex' : 'none';
}

// Process
processBtn.addEventListener('click', async () => {
  if (!currentFile) return;
  processBtn.disabled = true;
  progressWrap.classList.add('visible');
  progressBar.style.width = '20%';
  progressText.textContent = 'Uploading…';

  const fd = new FormData();
  fd.append('file', currentFile);
  fd.append('strength',    document.getElementById('strength').value / 100);
  fd.append('black_start', document.getElementById('blackStart').value / 100);
  fd.append('residual',    document.getElementById('residual').value / 100);
  fd.append('max_black',   document.getElementById('maxBlack').value / 100);
  fd.append('dpi',         document.getElementById('dpi').value);
  fd.append('out_format',  document.getElementById('outFormat').value);

  progressBar.style.width = '50%';
  progressText.textContent = 'Processing…';

  try {
    const resp = await fetch('/process', { method: 'POST', body: fd });
    if (!resp.ok) {
      const err = await resp.json();
      throw new Error(err.error || 'Processing failed');
    }

    progressBar.style.width = '90%';
    progressText.textContent = 'Downloading…';

    const blob = await resp.blob();
    const cd   = resp.headers.get('Content-Disposition') || '';
    const match = cd.match(/filename="?([^"]+)"?/);
    const outName = match ? match[1] : 'gcr_output.tif';

    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = outName;
    a.click();
    URL.revokeObjectURL(a.href);

    progressBar.style.width = '100%';
    progressText.textContent = 'Done ✓';
  } catch (err) {
    progressText.textContent = '❌ ' + err.message;
  }

  setTimeout(() => {
    progressWrap.classList.remove('visible');
    progressBar.style.width = '0%';
    processBtn.disabled = false;
  }, 2500);
});
</script>
</body>
</html>
"""


@app.route('/')
def index():
    return render_template_string(HTML)


@app.route('/process', methods=['POST'])
def process():
    f = request.files.get('file')
    if not f:
        return jsonify(error='No file uploaded'), 400

    strength    = float(request.form.get('strength', 0.7))
    black_start = float(request.form.get('black_start', 0.02))
    residual    = float(request.form.get('residual', 0.15))
    max_black   = float(request.form.get('max_black', 1.0))
    dpi         = int(request.form.get('dpi', 150))
    out_format  = request.form.get('out_format', 'tiff')

    suffix = Path(f.filename).suffix.lower()
    is_pdf = suffix == '.pdf'
    base   = Path(f.filename).stem

    tmp_dir = tempfile.mkdtemp(prefix='gcr_')
    in_path = os.path.join(tmp_dir, f.filename)
    f.save(in_path)

    try:
        if is_pdf:
            if not PDF2IMAGE_AVAILABLE:
                return jsonify(error='pdf2image is not installed — PDF support unavailable'), 400

            pages = convert_from_path(in_path, dpi=dpi)
            processed = []
            for page in pages:
                processed.append(process_image(page, strength, black_start, residual, max_black))

            if out_format == 'pdf':
                out_path = os.path.join(tmp_dir, base + '_gcr.pdf')
                rgb_pages = [p.convert('RGB') for p in processed]
                rgb_pages[0].save(out_path, save_all=True, append_images=rgb_pages[1:],
                                  resolution=dpi, quality=95)
                mime = 'application/pdf'
            else:
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
    port = 5050
    print(f'\n  GCR Tool running at http://localhost:{port}\n')
    threading.Timer(1.2, lambda: webbrowser.open(f'http://localhost:{port}')).start()
    app.run(host='127.0.0.1', port=port, debug=False)

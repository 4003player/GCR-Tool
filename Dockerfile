# ── GCR Tool Server ──
# Python Flask server for CMYK Gray Component Replacement

FROM python:3.11-slim

# Install poppler for PDF support (pdf2image) and libtiff for TIFF handling
RUN apt-get update && \
    apt-get install -y --no-install-recommends poppler-utils && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy server + GCR engine
COPY app.py gcr_tool.py ./

EXPOSE 8080

CMD ["python", "app.py"]

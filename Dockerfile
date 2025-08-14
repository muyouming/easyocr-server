# Multi-stage build for smaller image size
FROM python:3.9-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages with CPU-only PyTorch (much smaller)
RUN pip install --no-cache-dir --user \
    numpy \
    torch==2.0.1+cpu torchvision==0.15.2+cpu -f https://download.pytorch.org/whl/torch_stable.html \
    easyocr \
    bottle \
    gevent

# Final stage - runtime image
FROM python:3.9-slim

# Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libgthread-2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Set working directory
WORKDIR /app

# Copy only necessary application files
COPY main.py ocr.py requirements.txt ./
COPY examples ./examples

# Create upload directory
RUN mkdir -p upload model

# Download models at build time (optional - comment out if you want smaller image)
# This pre-downloads models to avoid runtime download delays
# RUN python -c "import easyocr; reader = easyocr.Reader(['en'], gpu=False)"

EXPOSE 8080

CMD ["python", "main.py"]
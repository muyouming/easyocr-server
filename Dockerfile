# Multi-stage build for smaller image size
FROM python:3.9-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    gcc \
    g++ \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Create a virtual environment to ensure clean dependency installation
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip and install wheel for better package handling
RUN pip install --upgrade pip wheel setuptools

# CRITICAL: Install NumPy 1.x first with no-deps to prevent upgrades
RUN pip install --no-cache-dir --no-deps numpy==1.24.3

# Install CPU-only PyTorch (compatible with NumPy 1.x)
RUN pip install --no-cache-dir \
    torch==2.0.1+cpu torchvision==0.15.2+cpu \
    -f https://download.pytorch.org/whl/torch_stable.html

# Install compatible dependencies for NumPy 1.24.3
RUN pip install --no-cache-dir \
    scipy==1.9.1 \
    scikit-image==0.20.0 \
    opencv-python-headless==4.7.0.72 \
    Pillow==9.5.0

# Install EasyOCR and remaining dependencies
RUN pip install --no-cache-dir --no-deps easyocr==1.7.0 && \
    pip install --no-cache-dir \
    bottle==0.12.25 \
    gevent==23.9.1 \
    pyclipper==1.3.0.post5 \
    python-bidi==0.4.2 \
    PyYAML==6.0.1 \
    shapely==2.0.2 \
    ninja==1.11.1

# Final stage - runtime image
FROM python:3.9-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libgthread-2.0-0 \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy the virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Set environment to use the virtual environment
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH="/opt/venv/lib/python3.9/site-packages"

# Set working directory
WORKDIR /app

# Create required directories
RUN mkdir -p upload model logs

# Copy application files
COPY main.py ocr.py requirements.txt ./
COPY examples ./examples

# Verify NumPy version is correct and test imports
RUN python -c "import numpy; assert numpy.__version__.startswith('1.24'), f'NumPy version {numpy.__version__} is not 1.24.x'; print(f'NumPy version: {numpy.__version__}')" && \
    python -c "import torch; print(f'PyTorch version: {torch.__version__}')" && \
    python -c "import torchvision; print(f'Torchvision version: {torchvision.__version__}')" && \
    python -c "import easyocr; print('EasyOCR imported successfully')"

# Expose port
EXPOSE 8080

# Set Python to run in unbuffered mode for better logging
ENV PYTHONUNBUFFERED=1

# Run the application
CMD ["python", "main.py"]
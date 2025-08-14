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

# Install NumPy first (required by other packages)
RUN pip install --no-cache-dir numpy==1.24.3

# Install CPU-only PyTorch
RUN pip install --no-cache-dir \
    torch==2.0.1+cpu torchvision==0.15.2+cpu \
    -f https://download.pytorch.org/whl/torch_stable.html

# Install other dependencies
RUN pip install --no-cache-dir \
    easyocr \
    bottle \
    gevent \
    Pillow \
    scipy

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

# Test that NumPy is working
RUN python -c "import numpy; print(f'NumPy version: {numpy.__version__}')"

# Expose port
EXPOSE 8080

# Set Python to run in unbuffered mode for better logging
ENV PYTHONUNBUFFERED=1

# Run the application
CMD ["python", "main.py"]
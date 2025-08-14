#!/bin/bash

echo "=== Docker Image Test Suite ==="
echo "Testing easyocr-optimized image on port 8086"
echo ""

# Test 1: Check if container is running
echo "1. Checking if container is running..."
if docker ps | grep -q easyocr-test; then
    echo "✓ Container is running"
else
    echo "✗ Container is not running"
    exit 1
fi

# Test 2: Check web interface
echo ""
echo "2. Testing web interface..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8086/ocr/)
if [ "$HTTP_CODE" = "200" ]; then
    echo "✓ Web interface is accessible (HTTP $HTTP_CODE)"
else
    echo "✗ Web interface failed (HTTP $HTTP_CODE)"
fi

# Test 3: Create a simple test image
echo ""
echo "3. Creating test image..."
cat > /tmp/test_ocr.py << 'EOF'
from PIL import Image, ImageDraw, ImageFont
import os

# Create a simple test image with text
img = Image.new('RGB', (400, 100), color='white')
draw = ImageDraw.Draw(img)

# Use default font
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
except:
    font = ImageFont.load_default()

draw.text((50, 30), "TEST OCR", fill='black', font=font)
img.save('/tmp/test_image.png')
print("Test image created at /tmp/test_image.png")
EOF

python3 /tmp/test_ocr.py

# Test 4: Test OCR with the simple image
echo ""
echo "4. Testing OCR functionality..."
echo "Sending request (this may take a while on first run due to model loading)..."

# Set timeout to 5 minutes for model download
RESPONSE=$(timeout 300 curl -s -X POST http://localhost:8086/ocr/ \
    -F "language=en" \
    -F "img_file=@/tmp/test_image.png" 2>/dev/null)

if [ $? -eq 124 ]; then
    echo "✗ Request timed out after 5 minutes"
elif [ -z "$RESPONSE" ]; then
    echo "✗ Empty response from server"
else
    echo "✓ Received response from server"
    echo "Response preview:"
    echo "$RESPONSE" | python3 -m json.tool 2>/dev/null | head -10 || echo "$RESPONSE" | head -10
fi

# Test 5: Check container resource usage
echo ""
echo "5. Container resource usage:"
docker stats --no-stream easyocr-test

# Test 6: Check container logs for errors
echo ""
echo "6. Recent container logs:"
docker logs easyocr-test --tail 10 2>&1 | grep -v "Progress:" | head -10

echo ""
echo "=== Test Complete ==="
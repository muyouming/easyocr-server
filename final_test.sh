#!/bin/bash

echo "=== Final Docker Test ==="
echo ""

PORT=8088
URL="http://localhost:$PORT/ocr/"

# 1. Wait for container to be ready
echo "1. Waiting for container to be ready..."
for i in {1..10}; do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" $URL 2>/dev/null)
    if [ "$HTTP_CODE" = "200" ]; then
        echo "✓ Container is ready!"
        break
    fi
    echo "  Waiting... ($i/10)"
    sleep 2
done

# 2. Test with example images
echo ""
echo "2. Testing with English example..."

# First request will download models if needed
echo "  Sending request (may take time for model download)..."
START=$(date +%s)
RESPONSE=$(curl -s -X POST $URL \
    -F "language=en" \
    -F "img_file=@examples/english.png" \
    --max-time 300)
END=$(date +%s)
DURATION=$((END - START))

if [ -n "$RESPONSE" ]; then
    echo "✓ Response received in ${DURATION}s"
    echo "  Response: $(echo $RESPONSE | python3 -c "import sys, json; data=json.load(sys.stdin); print('Detected:', len(data.get('summary_result', [])), 'text regions')" 2>/dev/null || echo $RESPONSE | head -c 100)"
else
    echo "✗ No response received"
fi

# 3. Second request (should be faster with cached model)
echo ""
echo "3. Testing with cached model..."
START=$(date +%s)
RESPONSE=$(curl -s -X POST $URL \
    -F "language=en" \
    -F "img_file=@examples/english.png" \
    --max-time 30)
END=$(date +%s)
DURATION=$((END - START))

if [ -n "$RESPONSE" ]; then
    echo "✓ Cached response in ${DURATION}s"
else
    echo "✗ Failed"
fi

# 4. Container stats
echo ""
echo "4. Container resource usage:"
docker stats easyocr-final --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}"

echo ""
echo "=== Test Complete ===
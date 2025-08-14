#!/bin/bash

echo "=== Quick Docker OCR Test ==="
echo ""

# Test 1: Web interface
echo "1. Testing web interface..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8087/ocr/)
if [ "$HTTP_CODE" = "200" ]; then
    echo "✓ Web interface is accessible"
else
    echo "✗ Web interface failed (HTTP $HTTP_CODE)"
fi

# Test 2: Container stats
echo ""
echo "2. Container statistics:"
docker stats easyocr-test-v2 --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"

# Test 3: Container logs (last 5 non-progress lines)
echo ""
echo "3. Recent container logs:"
docker exec easyocr-test-v2 tail -5 /proc/1/fd/1 2>/dev/null | grep -v Progress || echo "No recent logs"

# Test 4: Check if models are downloaded
echo ""
echo "4. Checking model directory:"
docker exec easyocr-test-v2 ls -la /root/.EasyOCR/model 2>/dev/null | head -10 || echo "Model directory not accessible"

# Test 5: Simple health check
echo ""
echo "5. Container health:"
docker inspect easyocr-test-v2 --format='Status: {{.State.Status}} | Running: {{.State.Running}} | Uptime: {{.State.StartedAt}}'

echo ""
echo "=== Test Complete ==="
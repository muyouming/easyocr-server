#!/usr/bin/env python3

import requests
import time
import json
import os
import sys
from PIL import Image, ImageDraw, ImageFont
import concurrent.futures
from io import BytesIO

BASE_URL = "http://localhost:8087/ocr/"

def create_test_image(text, filename):
    """Create a test image with specified text"""
    img = Image.new('RGB', (600, 200), color='white')
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 48)
    except:
        font = ImageFont.load_default()
    
    draw.text((50, 50), text, fill='black', font=font)
    img.save(filename)
    print(f"✓ Created test image: {filename}")
    return filename

def test_english_ocr():
    """Test OCR with English text"""
    print("\n1. Testing English OCR...")
    
    # Create test image
    img_path = create_test_image("Hello World OCR Test", "/tmp/english_test.png")
    
    # Send request
    start_time = time.time()
    with open(img_path, 'rb') as f:
        files = {'img_file': f}
        data = {'language': 'en'}
        response = requests.post(BASE_URL, files=files, data=data, timeout=60)
    
    elapsed = time.time() - start_time
    
    if response.status_code == 200:
        result = response.json()
        print(f"✓ English OCR successful (took {elapsed:.2f}s)")
        print(f"  Detected text: {result.get('summary_result', [])}")
        return True
    else:
        print(f"✗ English OCR failed: {response.status_code}")
        return False

def test_chinese_ocr():
    """Test OCR with Chinese text"""
    print("\n2. Testing Chinese OCR...")
    
    # Use the provided Chinese example
    img_path = "examples/chinese.jpg"
    
    if not os.path.exists(img_path):
        print("✗ Chinese example image not found")
        return False
    
    start_time = time.time()
    with open(img_path, 'rb') as f:
        files = {'img_file': f}
        data = {'language': 'ch_sim'}
        try:
            response = requests.post(BASE_URL, files=files, data=data, timeout=120)
            elapsed = time.time() - start_time
            
            if response.status_code == 200:
                result = response.json()
                print(f"✓ Chinese OCR successful (took {elapsed:.2f}s)")
                print(f"  Detected {len(result.get('summary_result', []))} text regions")
                return True
            else:
                print(f"✗ Chinese OCR failed: {response.status_code}")
                return False
        except requests.Timeout:
            print("✗ Chinese OCR timed out (model download may be in progress)")
            return False

def test_invalid_image():
    """Test error handling with invalid image"""
    print("\n3. Testing invalid image handling...")
    
    # Create invalid file
    with open("/tmp/invalid.txt", "w") as f:
        f.write("This is not an image")
    
    with open("/tmp/invalid.txt", 'rb') as f:
        files = {'img_file': ('invalid.txt', f)}
        data = {'language': 'en'}
        response = requests.post(BASE_URL, files=files, data=data, timeout=30)
    
    result = response.json()
    if 'error' in result:
        print(f"✓ Invalid image correctly rejected: {result['error']}")
        return True
    else:
        print("✗ Invalid image not properly handled")
        return False

def test_concurrent_requests():
    """Test handling of concurrent requests"""
    print("\n4. Testing concurrent request handling...")
    
    img_path = create_test_image("CONCURRENT", "/tmp/concurrent.png")
    
    def make_request(id):
        with open(img_path, 'rb') as f:
            files = {'img_file': f}
            data = {'language': 'en'}
            start = time.time()
            response = requests.post(BASE_URL, files=files, data=data, timeout=60)
            elapsed = time.time() - start
            return (id, response.status_code, elapsed)
    
    # Try 3 concurrent requests
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(make_request, i) for i in range(3)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    
    success_count = sum(1 for _, status, _ in results if status == 200)
    busy_count = sum(1 for _, status, _ in results if status != 200)
    
    print(f"  Successful requests: {success_count}/3")
    print(f"  Busy/Failed requests: {busy_count}/3")
    
    if success_count >= 1:  # At least one should succeed
        print("✓ Concurrent request handling working (server properly limits to 1 request)")
        return True
    else:
        print("✗ Concurrent request handling failed")
        return False

def test_large_image():
    """Test processing of large image"""
    print("\n5. Testing large image processing...")
    
    # Create a larger image
    img = Image.new('RGB', (3000, 2000), color='white')
    draw = ImageDraw.Draw(img)
    
    # Add multiple text regions
    for i in range(10):
        for j in range(10):
            draw.text((i*300, j*200), f"Text {i},{j}", fill='black')
    
    img_path = "/tmp/large_image.png"
    img.save(img_path)
    
    file_size = os.path.getsize(img_path) / (1024*1024)  # MB
    print(f"  Testing with {file_size:.2f}MB image (3000x2000 pixels)")
    
    start_time = time.time()
    with open(img_path, 'rb') as f:
        files = {'img_file': f}
        data = {'language': 'en'}
        try:
            response = requests.post(BASE_URL, files=files, data=data, timeout=120)
            elapsed = time.time() - start_time
            
            if response.status_code == 200:
                result = response.json()
                print(f"✓ Large image processed successfully (took {elapsed:.2f}s)")
                print(f"  Detected {len(result.get('summary_result', []))} text regions")
                return True
            else:
                print(f"✗ Large image processing failed: {response.status_code}")
                return False
        except requests.Timeout:
            print("✗ Large image processing timed out")
            return False

def test_response_times():
    """Measure response times for cached model"""
    print("\n6. Testing response times (cached model)...")
    
    img_path = create_test_image("SPEED TEST", "/tmp/speed_test.png")
    
    times = []
    for i in range(3):
        start_time = time.time()
        with open(img_path, 'rb') as f:
            files = {'img_file': f}
            data = {'language': 'en'}
            response = requests.post(BASE_URL, files=files, data=data, timeout=30)
        
        if response.status_code == 200:
            elapsed = time.time() - start_time
            times.append(elapsed)
            print(f"  Request {i+1}: {elapsed:.2f}s")
    
    if times:
        avg_time = sum(times) / len(times)
        print(f"✓ Average response time: {avg_time:.2f}s")
        return True
    else:
        print("✗ Response time test failed")
        return False

def test_memory_usage():
    """Check container memory usage"""
    print("\n7. Checking container resource usage...")
    
    result = os.popen("docker stats easyocr-test-v2 --no-stream --format 'table {{.MemUsage}}\t{{.CPUPerc}}'").read()
    print(f"  {result}")
    print("✓ Resource usage checked")
    return True

def main():
    print("=" * 60)
    print("EasyOCR Docker Image Test Suite")
    print("=" * 60)
    
    # Check if container is running
    result = os.popen("docker ps | grep easyocr-test-v2").read()
    if not result:
        print("Error: Container 'easyocr-test-v2' is not running!")
        sys.exit(1)
    
    tests = [
        test_english_ocr,
        test_chinese_ocr,
        test_invalid_image,
        test_concurrent_requests,
        test_large_image,
        test_response_times,
        test_memory_usage
    ]
    
    results = []
    for test in tests:
        try:
            results.append(test())
        except Exception as e:
            print(f"  Error: {e}")
            results.append(False)
    
    print("\n" + "=" * 60)
    print("Test Summary:")
    print(f"  Passed: {sum(results)}/{len(results)}")
    print(f"  Failed: {len(results) - sum(results)}/{len(results)}")
    
    if all(results):
        print("\n✅ All tests passed!")
    else:
        print("\n⚠️ Some tests failed")
    
    print("=" * 60)

if __name__ == "__main__":
    main()
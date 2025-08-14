import os
import sys
import logging
import signal
import argparse
import tempfile
import hashlib
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
from gevent import monkey

# Patch before importing other modules
monkey.patch_all()

from time import time
from bottle import request, run, post, get, response, abort
import json
from ocr import OCRProcessor
import gc
from threading import Lock, Thread
import threading

# Configuration class
class Config:
    """Application configuration"""
    # Server settings
    HOST = os.environ.get('OCR_HOST', '0.0.0.0')
    PORT = int(os.environ.get('OCR_PORT', 8080))
    DEBUG = os.environ.get('OCR_DEBUG', 'false').lower() == 'true'
    
    # Processing settings
    IDLE_TIMEOUT = int(os.environ.get('OCR_IDLE_TIMEOUT', 300))  # 5 minutes
    MAX_IMAGE_SIZE = int(os.environ.get('OCR_MAX_IMAGE_SIZE', 4096))  # pixels
    MAX_FILE_SIZE = int(os.environ.get('OCR_MAX_FILE_SIZE', 10)) * 1024 * 1024  # MB to bytes
    ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.webp'}
    
    # Paths
    UPLOAD_DIR = Path(os.environ.get('OCR_UPLOAD_DIR', 'upload'))
    MODEL_DIR = Path(os.environ.get('OCR_MODEL_DIR', 'model'))
    LOG_DIR = Path(os.environ.get('OCR_LOG_DIR', 'logs'))
    
    # Logging
    LOG_LEVEL = os.environ.get('OCR_LOG_LEVEL', 'INFO')
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Performance
    USE_GPU = os.environ.get('OCR_USE_GPU', 'false').lower() == 'true'
    DEFAULT_LANGUAGES = os.environ.get('OCR_DEFAULT_LANGUAGES', 'en')
    MAX_CONCURRENT_REQUESTS = int(os.environ.get('OCR_MAX_CONCURRENT', 1))
    REQUEST_TIMEOUT = int(os.environ.get('OCR_REQUEST_TIMEOUT', 120))  # seconds

# Setup logging
def setup_logging():
    """Configure application logging"""
    Config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    log_file = Config.LOG_DIR / f"easyocr_{datetime.now().strftime('%Y%m%d')}.log"
    
    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL),
        format=Config.LOG_FORMAT,
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    return logging.getLogger(__name__)

# Global variables
logger = setup_logging()
ocr_processor = None
request_lock = Lock()
cleanup_thread = None
shutdown_event = threading.Event()
request_counter = 0
total_processing_time = 0

# Statistics tracking
class Stats:
    """Track application statistics"""
    def __init__(self):
        self.reset()
    
    def reset(self):
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.total_processing_time = 0
        self.start_time = time()
    
    def add_request(self, success=True, processing_time=0):
        self.total_requests += 1
        if success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1
        self.total_processing_time += processing_time
    
    def get_stats(self):
        uptime = time() - self.start_time
        avg_processing_time = (self.total_processing_time / self.successful_requests 
                              if self.successful_requests > 0 else 0)
        
        return {
            'uptime_seconds': uptime,
            'total_requests': self.total_requests,
            'successful_requests': self.successful_requests,
            'failed_requests': self.failed_requests,
            'average_processing_time': avg_processing_time,
            'success_rate': (self.successful_requests / self.total_requests * 100 
                           if self.total_requests > 0 else 0)
        }

stats = Stats()

def ensure_directories():
    """Ensure required directories exist"""
    for directory in [Config.UPLOAD_DIR, Config.MODEL_DIR, Config.LOG_DIR]:
        directory.mkdir(parents=True, exist_ok=True)
    logger.info(f"Directories initialized: upload={Config.UPLOAD_DIR}, model={Config.MODEL_DIR}, log={Config.LOG_DIR}")

def cleanup_old_files():
    """Clean up old temporary files"""
    try:
        now = time()
        for file_path in Config.UPLOAD_DIR.glob('*'):
            if file_path.is_file():
                file_age = now - file_path.stat().st_mtime
                if file_age > 3600:  # 1 hour old
                    file_path.unlink()
                    logger.debug(f"Cleaned up old file: {file_path}")
    except Exception as e:
        logger.error(f"Error during file cleanup: {e}")

def periodic_cleanup():
    """Periodic cleanup task"""
    while not shutdown_event.is_set():
        try:
            # Check and cleanup processor
            check_and_cleanup_processor()
            # Clean old files
            cleanup_old_files()
            # Wait for next cleanup cycle
            shutdown_event.wait(60)  # Check every minute
        except Exception as e:
            logger.error(f"Error in periodic cleanup: {e}")

def check_and_cleanup_processor():
    """Check if processor is idle and clean it up if necessary"""
    global ocr_processor
    
    if ocr_processor and (time() - ocr_processor.last_used) > Config.IDLE_TIMEOUT:
        logger.info("Cleaning up idle OCR processor")
        try:
            ocr_processor.cleanup()
            ocr_processor = None
            gc.collect()
            logger.info("OCR processor cleaned up successfully")
        except Exception as e:
            logger.error(f"Error cleaning up OCR processor: {e}")

def is_valid_image(filename):
    """Check if the file is a valid image"""
    if not filename:
        return False
    ext = os.path.splitext(filename)[1].lower()
    return ext in Config.ALLOWED_EXTENSIONS

def generate_safe_filename(original_filename):
    """Generate a safe filename for uploaded file"""
    timestamp = str(time()).replace('.', '')
    hash_suffix = hashlib.md5(original_filename.encode()).hexdigest()[:8]
    ext = os.path.splitext(original_filename)[1].lower()
    return f"{timestamp}_{hash_suffix}{ext}"

@contextmanager
def temporary_file(upload_file):
    """Context manager for handling temporary uploaded files"""
    temp_path = None
    try:
        # Generate safe filename
        safe_filename = generate_safe_filename(upload_file.filename)
        temp_path = Config.UPLOAD_DIR / safe_filename
        
        # Save uploaded file
        upload_file.save(str(temp_path), overwrite=True)
        
        # Check file size
        file_size = temp_path.stat().st_size
        if file_size > Config.MAX_FILE_SIZE:
            raise ValueError(f"File too large: {file_size} bytes (max: {Config.MAX_FILE_SIZE} bytes)")
        
        yield str(temp_path)
        
    finally:
        # Clean up temp file
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except Exception as e:
                logger.warning(f"Failed to delete temp file {temp_path}: {e}")

def initialize_processor(languages):
    """Initialize or update the OCR processor"""
    global ocr_processor
    
    language_list = languages.split(',') if isinstance(languages, str) else languages
    
    # Check if we need to reinitialize
    if ocr_processor is None or ocr_processor.languages != language_list:
        logger.info(f"Initializing OCR processor for languages: {language_list}")
        
        # Clean up old processor
        if ocr_processor:
            ocr_processor.cleanup()
        
        # Create new processor
        ocr_processor = OCRProcessor(
            language_list,
            gpu=Config.USE_GPU,
            max_image_dimension=Config.MAX_IMAGE_SIZE
        )
        
        logger.info(f"OCR processor initialized in {ocr_processor.init_time:.2f}s")
    
    return ocr_processor

# API Endpoints
@post('/ocr/')
@post('/ocr')
def ocr_post():
    """Handle OCR POST requests"""
    global request_counter
    request_id = f"req_{time()}_{request_counter}"
    request_counter += 1
    
    logger.info(f"[{request_id}] New OCR request received")
    start_time = time()
    
    # Set response headers
    response.content_type = 'application/json'
    
    # Try to acquire lock
    if not request_lock.acquire(blocking=False):
        logger.warning(f"[{request_id}] Server busy, rejecting request")
        stats.add_request(success=False)
        response.status = 503  # Service Unavailable
        return json.dumps({
            'error': 'Server is busy processing another request. Please try again later.',
            'request_id': request_id
        })
    
    try:
        # Validate input
        upload_file = request.files.get('img_file')
        if not upload_file:
            logger.warning(f"[{request_id}] No file uploaded")
            stats.add_request(success=False)
            response.status = 400
            return json.dumps({
                'error': 'No file uploaded',
                'request_id': request_id
            })
        
        if not is_valid_image(upload_file.filename):
            logger.warning(f"[{request_id}] Invalid file type: {upload_file.filename}")
            stats.add_request(success=False)
            response.status = 400
            return json.dumps({
                'error': f'Invalid file type. Allowed: {", ".join(Config.ALLOWED_EXTENSIONS)}',
                'request_id': request_id
            })
        
        # Get language parameter
        language = request.forms.get('language', Config.DEFAULT_LANGUAGES)
        logger.info(f"[{request_id}] Processing {upload_file.filename} with languages: {language}")
        
        # Process the image
        with temporary_file(upload_file) as temp_path:
            # Check and cleanup idle processor
            check_and_cleanup_processor()
            
            # Initialize processor if needed
            processor = initialize_processor(language)
            
            # Process the image
            results = processor.process_image(temp_path)
            
            # Add metadata
            results['request_id'] = request_id
            results['processing_time'] = time() - start_time
            
            # Log results
            if results.get('error'):
                logger.error(f"[{request_id}] OCR error: {results['error']}")
                stats.add_request(success=False)
                response.status = 500
            else:
                text_count = len(results.get('summary_result', []))
                logger.info(f"[{request_id}] OCR successful: {text_count} text regions detected in {results['processing_time']:.2f}s")
                stats.add_request(success=True, processing_time=results['processing_time'])
            
            return json.dumps(results)
            
    except Exception as e:
        logger.exception(f"[{request_id}] Unexpected error: {e}")
        stats.add_request(success=False)
        response.status = 500
        return json.dumps({
            'error': f'Internal server error: {str(e)}',
            'request_id': request_id
        })
        
    finally:
        request_lock.release()
        gc.collect()

@get('/ocr/')
@get('/ocr')
def ocr_get():
    """Serve the web interface"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>EasyOCR Server</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
                background: #f5f5f5;
            }
            .container {
                background: white;
                border-radius: 8px;
                padding: 30px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            h1 {
                color: #333;
                border-bottom: 2px solid #4CAF50;
                padding-bottom: 10px;
            }
            .form-group {
                margin-bottom: 20px;
            }
            label {
                display: block;
                margin-bottom: 5px;
                font-weight: bold;
                color: #555;
            }
            input[type="file"], select {
                width: 100%;
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 4px;
                box-sizing: border-box;
            }
            button {
                background-color: #4CAF50;
                color: white;
                padding: 12px 30px;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 16px;
                width: 100%;
            }
            button:hover {
                background-color: #45a049;
            }
            button:disabled {
                background-color: #cccccc;
                cursor: not-allowed;
            }
            #results {
                width: 100%;
                min-height: 200px;
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-family: monospace;
                font-size: 14px;
                background: #f9f9f9;
            }
            .status {
                padding: 10px;
                margin-top: 10px;
                border-radius: 4px;
                display: none;
            }
            .status.info {
                background: #e3f2fd;
                color: #1976d2;
                border: 1px solid #1976d2;
            }
            .status.error {
                background: #ffebee;
                color: #c62828;
                border: 1px solid #c62828;
            }
            .status.success {
                background: #e8f5e9;
                color: #2e7d32;
                border: 1px solid #2e7d32;
            }
        </style>
        <script src="https://cdn.jsdelivr.net/npm/jquery@3.6.0/dist/jquery.min.js"></script>
    </head>
    <body>
        <div class="container">
            <h1>🔍 EasyOCR Server</h1>
            
            <div class="form-group">
                <label for="imgFile">Select Image File</label>
                <input type="file" id="imgFile" accept=".jpg,.jpeg,.png,.tiff,.tif,.bmp,.webp" />
            </div>
            
            <div class="form-group">
                <label for="language">Language</label>
                <select id="language">
                    <option value="en" selected>English</option>
                    <option value="ch_sim">Simplified Chinese</option>
                    <option value="ch_tra">Traditional Chinese</option>
                    <option value="en,ch_sim">English + Simplified Chinese</option>
                    <option value="ja">Japanese</option>
                    <option value="ko">Korean</option>
                    <option value="es">Spanish</option>
                    <option value="fr">French</option>
                    <option value="de">German</option>
                    <option value="ru">Russian</option>
                    <option value="ar">Arabic</option>
                    <option value="hi">Hindi</option>
                    <option value="th">Thai</option>
                    <option value="vi">Vietnamese</option>
                </select>
            </div>
            
            <div class="form-group">
                <button id="processBtn">Process Image</button>
            </div>
            
            <div id="status" class="status"></div>
            
            <div class="form-group">
                <label for="results">Results</label>
                <textarea id="results" readonly placeholder="OCR results will appear here..."></textarea>
            </div>
        </div>
        
        <script>
            $(function() {
                $('#processBtn').on('click', function() {
                    const files = $('#imgFile')[0].files;
                    if (files.length <= 0) {
                        showStatus('Please select an image file', 'error');
                        return;
                    }
                    
                    // Check file size (10MB limit)
                    if (files[0].size > 10 * 1024 * 1024) {
                        showStatus('File size exceeds 10MB limit', 'error');
                        return;
                    }
                    
                    const formData = new FormData();
                    formData.append('img_file', files[0]);
                    formData.append('language', $('#language').val());
                    
                    showStatus('Processing image...', 'info');
                    $('#processBtn').prop('disabled', true);
                    $('#results').val('');
                    
                    $.ajax({
                        url: '/ocr/',
                        type: 'POST',
                        data: formData,
                        contentType: false,
                        processData: false,
                        cache: false,
                        timeout: 120000, // 2 minute timeout
                        success: function(res) {
                            $('#results').val(JSON.stringify(res, null, 2));
                            
                            if (res.error) {
                                showStatus('Error: ' + res.error, 'error');
                            } else {
                                const count = res.summary_result ? res.summary_result.length : 0;
                                showStatus(`Success! Detected ${count} text regions in ${res.processing_time?.toFixed(2)}s`, 'success');
                            }
                        },
                        error: function(xhr, status, error) {
                            let errorMsg = 'Request failed';
                            if (xhr.responseJSON && xhr.responseJSON.error) {
                                errorMsg = xhr.responseJSON.error;
                            } else if (status === 'timeout') {
                                errorMsg = 'Request timed out';
                            } else {
                                errorMsg = error || status;
                            }
                            
                            $('#results').val('Error: ' + errorMsg);
                            showStatus('Error: ' + errorMsg, 'error');
                        },
                        complete: function() {
                            $('#processBtn').prop('disabled', false);
                        }
                    });
                });
                
                function showStatus(message, type) {
                    $('#status')
                        .removeClass('info error success')
                        .addClass(type)
                        .text(message)
                        .show();
                    
                    if (type !== 'info') {
                        setTimeout(() => $('#status').fadeOut(), 5000);
                    }
                }
            });
        </script>
    </body>
    </html>
    '''

@get('/health')
@get('/health/')
def health_check():
    """Health check endpoint"""
    response.content_type = 'application/json'
    
    health_status = {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'processor_loaded': ocr_processor is not None,
        'upload_dir_writable': os.access(Config.UPLOAD_DIR, os.W_OK)
    }
    
    if ocr_processor:
        health_status['processor_languages'] = ocr_processor.languages
        health_status['processor_idle_time'] = time() - ocr_processor.last_used
    
    return json.dumps(health_status)

@get('/stats')
@get('/stats/')
def get_stats():
    """Get server statistics"""
    response.content_type = 'application/json'
    return json.dumps(stats.get_stats())

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    logger.info(f"Received signal {signum}, shutting down...")
    shutdown_event.set()
    
    # Cleanup
    global ocr_processor
    if ocr_processor:
        ocr_processor.cleanup()
    
    # Wait for cleanup thread
    if cleanup_thread and cleanup_thread.is_alive():
        cleanup_thread.join(timeout=5)
    
    logger.info("Shutdown complete")
    sys.exit(0)

def main():
    """Main application entry point"""
    parser = argparse.ArgumentParser(description='EasyOCR Server')
    parser.add_argument('--host', default=Config.HOST, help='Host to bind to')
    parser.add_argument('--port', type=int, default=Config.PORT, help='Port to bind to')
    parser.add_argument('--debug', action='store_true', default=Config.DEBUG, help='Enable debug mode')
    parser.add_argument('--gpu', action='store_true', default=Config.USE_GPU, help='Use GPU acceleration')
    
    args = parser.parse_args()
    
    # Update config with command line arguments
    Config.HOST = args.host
    Config.PORT = args.port
    Config.DEBUG = args.debug
    Config.USE_GPU = args.gpu
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Ensure directories exist
    ensure_directories()
    
    # Start cleanup thread
    global cleanup_thread
    cleanup_thread = Thread(target=periodic_cleanup, daemon=True)
    cleanup_thread.start()
    
    # Log startup information
    logger.info("=" * 60)
    logger.info("EasyOCR Server Starting")
    logger.info(f"Host: {Config.HOST}")
    logger.info(f"Port: {Config.PORT}")
    logger.info(f"Debug: {Config.DEBUG}")
    logger.info(f"GPU: {Config.USE_GPU}")
    logger.info(f"Max file size: {Config.MAX_FILE_SIZE / 1024 / 1024:.1f}MB")
    logger.info(f"Max image dimension: {Config.MAX_IMAGE_SIZE}px")
    logger.info(f"Idle timeout: {Config.IDLE_TIMEOUT}s")
    logger.info(f"Upload directory: {Config.UPLOAD_DIR}")
    logger.info(f"Model directory: {Config.MODEL_DIR}")
    logger.info("=" * 60)
    
    # Start server
    try:
        run(
            host=Config.HOST,
            port=Config.PORT,
            debug=Config.DEBUG,
            server='gevent',
            quiet=not Config.DEBUG
        )
    except Exception as e:
        logger.exception(f"Server failed to start: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
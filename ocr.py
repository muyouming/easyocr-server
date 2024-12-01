import sys
import easyocr
from time import time
from json import dump
import gc
from PIL import Image
import os

class OCRProcessor:
    def __init__(self, languages, gpu=False, max_image_dimension=1024):
        """Initialize the OCR processor with specified languages.
        
        Args:
            languages (list): List of language codes
            gpu (bool): Whether to use GPU acceleration
            max_image_dimension (int): Maximum dimension (width/height) for input images
        """
        self.languages = languages if isinstance(languages, list) else languages.split(',')
        self.init_time = 0
        self.max_image_dimension = max_image_dimension
        self.last_used = time()
        
        init_start = time()
        self.reader = easyocr.Reader(
            self.languages,
            gpu=gpu,
            model_storage_directory='model/.',
            user_network_directory='model/.',
        )
        init_end = time()
        self.init_time = init_end - init_start

    def resize_image(self, image_path):
        """Resize image if it exceeds maximum dimensions."""
        with Image.open(image_path) as img:
            # Convert to RGB if necessary
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Check if resize is needed
            w, h = img.size
            if w > self.max_image_dimension or h > self.max_image_dimension:
                ratio = min(self.max_image_dimension/w, self.max_image_dimension/h)
                new_size = (int(w*ratio), int(h*ratio))
                img = img.resize(new_size, Image.LANCZOS)
                
                # Save resized image
                resized_path = f"{image_path}_resized.jpg"
                img.save(resized_path, 'JPEG', quality=95)
                return resized_path
            
            return image_path

    def process_image(self, img_filename):
        """Process an image file and return OCR results."""
        self.last_used = time()
        
        ocr_results = {
            'language': self.languages,
            'init_take': self.init_time,
            'ocr_take': 0.0,
            'summary_result': [],
            'full_result': [],
            'error': ''
        }

        try:
            # Resize image if necessary
            processed_img_path = self.resize_image(img_filename)
            
            ocr_start = time()
            result = self.reader.readtext(processed_img_path)
            
            for _res in result:
                ocr_results['summary_result'].append(_res[1])
                _res_0_conversion = [[0, 0], [0, 0], [0, 0], [0, 0]]
                for _i in range(len(_res[0])):
                    _res_0_conversion[_i] = [int(_res[0][_i][0]), int(_res[0][_i][1])]
                ocr_results['full_result'].append({
                    'bounding_box': _res_0_conversion,
                    'text_detected': _res[1],
                    'confident_level': _res[2],
                })
            ocr_end = time()
            ocr_results['ocr_take'] = ocr_end - ocr_start
            
            # Clean up
            if processed_img_path != img_filename:
                os.remove(processed_img_path)
            
        except Exception as e:
            ocr_results['error'] = str(e)
        
        # Force garbage collection
        gc.collect()
            
        return ocr_results

    def save_results(self, results, output_filename):
        """Save OCR results to a JSON file.
        
        Args:
            results (dict): OCR results to save
            output_filename (str): Path to save the JSON file
        """
        with open(output_filename, 'w', encoding='UTF-8') as f:
            dump(results, f)

    def cleanup(self):
        """Clean up resources."""
        self.reader = None
        gc.collect()

def main():
    if len(sys.argv) < 3:
        print("Usage: python ocr.py <image_file> <languages>")
        sys.exit(1)
        
    img_filename = sys.argv[1]
    languages = sys.argv[2]
    
    processor = OCRProcessor(languages)
    results = processor.process_image(img_filename)
    processor.save_results(results, f'{img_filename}.json')

if __name__ == "__main__":
    main()

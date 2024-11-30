import sys
import easyocr
from time import time
from json import dump

class OCRProcessor:
    def __init__(self, languages, gpu=False):
        """Initialize the OCR processor with specified languages.
        
        Args:
            languages (list): List of language codes
            gpu (bool): Whether to use GPU acceleration
        """
        self.languages = languages if isinstance(languages, list) else languages.split(',')
        self.init_time = 0
        
        init_start = time()
        self.reader = easyocr.Reader(
            self.languages,
            gpu=gpu,
            model_storage_directory='model/.',
            user_network_directory='model/.',
        )
        init_end = time()
        self.init_time = init_end - init_start

    def process_image(self, img_filename):
        """Process an image file and return OCR results.
        
        Args:
            img_filename (str): Path to the image file
            
        Returns:
            dict: OCR results including timing and detected text
        """
        ocr_results = {
            'language': self.languages,
            'init_take': self.init_time,
            'ocr_take': 0.0,
            'summary_result': [],
            'full_result': [],
            'error': ''
        }

        try:
            ocr_start = time()
            result = self.reader.readtext(img_filename)
            
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
            
        except Exception as e:
            ocr_results['error'] = str(e)
            
        return ocr_results

    def save_results(self, results, output_filename):
        """Save OCR results to a JSON file.
        
        Args:
            results (dict): OCR results to save
            output_filename (str): Path to save the JSON file
        """
        with open(output_filename, 'w', encoding='UTF-8') as f:
            dump(results, f)

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

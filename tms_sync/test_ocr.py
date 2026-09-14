"""
test_ocr.py
===========
Quick smoke test to confirm Tesseract is installed and working before
running the real pipeline against it.

Run:
    python test_ocr.py path/to/sample_bill.png
"""
import sys
import pytesseract
from PIL import Image

if __name__ == "__main__":
    image_path = sys.argv[1] if len(sys.argv) > 1 else "sample_bill.png"
    print(f"Tesseract version: {pytesseract.get_tesseract_version()}")
    text = pytesseract.image_to_string(Image.open(image_path))
    print(f"\nExtracted {len(text)} characters from {image_path}:\n")
    print(text)
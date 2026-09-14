"""
debug_preprocess.py
=====================
Standalone debug tool - NOT part of the main pipeline, doesn't touch
ocr_ingest.py or the database at all.

Saves the PREPROCESSED version of an image to disk (the upscaled,
grayscale, sharpened version that Tesseract now actually reads) so you
can open it yourself and visually confirm what changed - no trust
required, just look at it directly.

Usage:
    python debug_preprocess.py "scanned_bills\processed\FRHT 4.png"

This creates a new file next to the original, named
"<original>_preprocessed.png", which you can open like any other image.
"""
import sys
import os
from ocr_ingest import _preprocess_for_ocr

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python debug_preprocess.py path\\to\\image.png")
        sys.exit(1)

    image_path = sys.argv[1]
    preprocessed = _preprocess_for_ocr(image_path)

    base, ext = os.path.splitext(image_path)
    output_path = f"{base}_preprocessed.png"
    preprocessed.save(output_path)

    print(f"Original:      {image_path}")
    print(f"Preprocessed:  {output_path}")
    print("Open both side by side to compare - the preprocessed one is what Tesseract actually reads now.")
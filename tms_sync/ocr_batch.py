"""
ocr_batch.py
============
Scans the scanned_bills/ folder for bill images, runs each one through
the OCR pipeline, and inserts results into freight_bill + freight_bill_details.

This is the OCR equivalent of sync_freight_bills() in sync_tables.py -
same destination tables, different source (scanned images instead of TMS API).

Processed images are moved to scanned_bills/processed/ so re-running
main_sync.py doesn't re-process the same bill twice.
"""

import os
import shutil
from ocr_ingest import ingest_bill_image

SCAN_FOLDER = "scanned_bills"
PROCESSED_FOLDER = os.path.join(SCAN_FOLDER, "processed")
FAILED_FOLDER = os.path.join(SCAN_FOLDER, "failed")

VALID_EXTENSIONS = (".png", ".jpg", ".jpeg", ".pdf")


def sync_scanned_bills():
    """
    Processes every image in scanned_bills/ that hasn't been processed yet.
    Call this from main_sync.py alongside the TMS sync steps.
    """
    os.makedirs(SCAN_FOLDER, exist_ok=True)
    os.makedirs(PROCESSED_FOLDER, exist_ok=True)
    os.makedirs(FAILED_FOLDER, exist_ok=True)

    files_to_process = [
        f for f in os.listdir(SCAN_FOLDER)
        if f.lower().endswith(VALID_EXTENSIONS)
    ]

    if not files_to_process:
        print("  No new scanned bills to process.")
        return

    print(f"  Found {len(files_to_process)} scanned bill(s) to process.")

    for filename in files_to_process:
        filepath = os.path.join(SCAN_FOLDER, filename)
        print(f"\n  Processing: {filename}")

        try:
            parsed = ingest_bill_image(filepath, dry_run=False)

            if parsed.get("validated"):
                # Success - move to processed/ so it's not re-run next time
                shutil.move(filepath, os.path.join(PROCESSED_FOLDER, filename))
                print(f"  -> Moved to processed/")
            else:
                # Extraction ran but validation failed (e.g. totals don't match)
                # Move to failed/ for manual review instead of leaving it stuck
                shutil.move(filepath, os.path.join(FAILED_FOLDER, filename))
                print(f"  -> Validation failed. Moved to failed/ for manual review.")

        except Exception as e:
            print(f"  -> ERROR processing {filename}: {e}")
            shutil.move(filepath, os.path.join(FAILED_FOLDER, filename))


if __name__ == "__main__":
    sync_scanned_bills()

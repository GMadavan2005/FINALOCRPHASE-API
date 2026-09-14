"""
verify_bills.py
================
Runs every bill in a folder through the real pipeline and prints a clean,
one-line-per-file report: which extraction method was used (PDF text
layer vs Tesseract), which carrier matched, the invoice number, the
total, and whether it validated -- so you can eyeball every single bill
BEFORE trusting main_sync.py to actually write to the database.

Two modes:

  1. No database needed (extraction + parsing only):
         python verify_bills.py path/to/folder --no-db

     This proves OCR/PDF-handling and bill_parser.py are working, but
     can't tell you the carrier match (that needs live carrier_master)
     or whether the DB write itself would succeed.

  2. Full check (needs your real .env / db.py working):
         python verify_bills.py path/to/folder

     This is the real test -- it calls ingest_bill_image(dry_run=True)
     for every file, which does everything main_sync.py would do
     EXCEPT the final INSERT/UPDATE, including the live carrier_master
     lookup.

Either way, nothing in this script writes to the database (dry_run is
hardcoded True) -- it's purely diagnostic.
"""
import argparse
import os
import sys

VALID_EXTENSIONS = (".png", ".jpg", ".jpeg", ".pdf")


def extract_with_source(path: str) -> tuple[str, str]:
    """Run the same first-pass OCR path as the production pipeline."""
    import ocr_ingest as oi

    if path.lower().endswith(".pdf"):
        return oi._ocr_pdf_pages(path), "tesseract(pdf)"
    return oi._ocr_image(path), "tesseract"


def run_no_db(folder: str) -> None:
    from bill_parser import parse_freight_bill

    files = sorted(f for f in os.listdir(folder) if f.lower().endswith(VALID_EXTENSIONS))
    if not files:
        print(f"No bill files found in {folder}")
        return

    print(f"{'file':<20} {'source':<12} {'bill#':<10} {'date':<12} {'total':>12} {'items':>6} {'validated':>10}")
    print("-" * 90)
    n_ok = 0
    for filename in files:
        path = os.path.join(folder, filename)
        try:
            text, source = extract_with_source(path)
            result = parse_freight_bill(text)
            ok = result["validated"]
            n_ok += ok
            print(f"{filename:<20} {source:<12} {str(result['freightBillNumber']):<10} "
                  f"{str(result['invoiceDate']):<12} {str(result['freightAmount']):>12} "
                  f"{len(result['details']):>6} {str(ok):>10}")
            if result["warnings"]:
                for w in result["warnings"]:
                    print(f"    ! {w}")
        except Exception as e:
            print(f"{filename:<20} ERROR: {e}")
    print("-" * 90)
    print(f"{n_ok}/{len(files)} validated (extraction + parsing only -- carrier match and DB write NOT checked)")


def run_with_db(folder: str) -> None:
    from ocr_ingest import ingest_bill_image

    files = sorted(f for f in os.listdir(folder) if f.lower().endswith(VALID_EXTENSIONS))
    if not files:
        print(f"No bill files found in {folder}")
        return

    results = []
    for filename in files:
        path = os.path.join(folder, filename)
        print(f"\n{'='*70}\n{filename}\n{'='*70}")
        try:
            parsed = ingest_bill_image(path, dry_run=True)
            results.append((filename, parsed))
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append((filename, None))

    print(f"\n\n{'='*70}\nSUMMARY\n{'='*70}")
    print(f"{'file':<20} {'carrier':<18} {'bill#':<10} {'total':>12} {'validated':>10}")
    n_ok = 0
    for filename, parsed in results:
        if parsed is None:
            print(f"{filename:<20} ERROR")
            continue
        ok = parsed.get("validated") and parsed.get("carrierCode") is not None
        n_ok += ok
        print(f"{filename:<20} {str(parsed.get('carrierCode')):<18} "
              f"{str(parsed.get('freightBillNumber')):<10} {str(parsed.get('freightAmount')):>12} "
              f"{str(ok):>10}")
    print(f"\n{n_ok}/{len(results)} would insert cleanly (dry run -- nothing written)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder")
    parser.add_argument("--no-db", action="store_true",
                         help="Skip carrier_master lookup and DB dry-run; only test extraction + parsing.")
    args = parser.parse_args()

    if args.no_db:
        run_no_db(args.folder)
    else:
        run_with_db(args.folder)

"""
full_pipeline_demo.py
======================
Runs ONE bill image through the ENTIRE real pipeline, stage by stage,
printing what happens at each step so you can see exactly what's
picked up and where.

Usage:
    python full_pipeline_demo.py test_bills\FRHT_5.png
    python full_pipeline_demo.py test_bills\FRHT_5.png --insert

Without --insert: everything runs (OCR, parsing, carrier match against
your REAL carrier_master table) but nothing is written to the database -
safe to run over and over while testing.

With --insert: same as above, but if parsing validated AND a carrier
matched, it actually writes to freight_bill + freight_bill_details in
your real Postgres database.
"""
import sys
import json

from ocr_ingest import extract_raw_text, get_known_carriers, upsert_freight_bill
from bill_parser import parse_freight_bill, match_carrier


def run(image_path: str, do_insert: bool):
    print("=" * 80)
    print(f"BILL: {image_path}")
    print("=" * 80)

    # ---- STAGE 1: EXTRACTION ----
    print("\n[STAGE 1] EXTRACTION - running OCR on the image")
    print("-" * 80)
    raw_text = extract_raw_text(image_path)
    print(raw_text)
    print("-" * 80)
    print(f"({len(raw_text)} characters extracted)")

    # ---- STAGE 2: PARSING ----
    print("\n[STAGE 2] PARSING - pulling invoice #, date, total, line items out of that text")
    print("-" * 80)
    parsed = parse_freight_bill(raw_text)
    print(json.dumps(
        {k: v for k, v in parsed.items() if k != "details"},
        indent=2,
    ))
    print(f"Line items found: {len(parsed['details'])}")
    for d in parsed["details"]:
        print(f"  Load {d['userReferenceNumber']}: {d['freightBillDetailTotal']:.2f}")

    # ---- STAGE 3: CARRIER MATCH ----
    print("\n[STAGE 3] CARRIER MATCH - identifying which carrier issued this bill")
    print("-" * 80)
    known_carriers = get_known_carriers()
    print(f"Checking against {len(known_carriers)} known carriers from carrier_master: {known_carriers}")
    carrier_match = match_carrier(raw_text, known_carriers)
    if carrier_match:
        print(f"MATCHED: {carrier_match['carrierName']} ({carrier_match['carrierCode']}), "
              f"confidence {carrier_match['score']:.2f}")
        parsed["carrierCode"] = carrier_match["carrierCode"]
    else:
        print("NO CONFIDENT MATCH - this bill would be skipped, not inserted.")
        parsed["carrierCode"] = None

    # ---- STAGE 4: DECISION + DB WRITE ----
    print("\n[STAGE 4] DATABASE WRITE")
    print("-" * 80)
    if not parsed["validated"]:
        print("SKIPPED: parsing did not validate (line items don't sum to stated total, "
              "or a required field is missing). Nothing written.")
        return
    if parsed["carrierCode"] is None:
        print("SKIPPED: no confident carrier match. Nothing written.")
        return
    if not do_insert:
        print("DRY RUN: everything above looks good, but --insert was not passed, "
              "so nothing was written to the database.")
        return

    outcome = upsert_freight_bill(parsed)
    print(f"DONE: {outcome.upper()} - {parsed['carrierCode']}/{parsed['freightBillNumber']} "
          f"({len(parsed['details'])} line items, total {parsed['freightAmount']})")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python full_pipeline_demo.py path\\to\\bill.png [--insert]")
        sys.exit(1)
    run(sys.argv[1], do_insert="--insert" in sys.argv)

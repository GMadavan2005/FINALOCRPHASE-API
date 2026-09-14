"""
ocr_ingest.py
=============
Takes a scanned freight bill (image or PDF page), runs it through
Tesseract, parses the result, validates it, and inserts it into
freight_bill + freight_bill_details.

Uses Tesseract (pytesseract) rather than PaddleOCR: much lighter to load
and run, at the cost of somewhat lower accuracy on messy scans than
PaddleOCR's deep-learning models -- an acceptable trade for the speed on
these mostly-clean, machine-rendered invoices.

PDF and image handling both use Tesseract. PDFs are rendered to images
first, so both file types follow the same OCR and validation rules.

Run standalone:
    python ocr_ingest.py path/to/bill.png

Or import and call ingest_bill_image() from main_sync.py.
"""
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"E:\tesseract\tesseract.exe"
import os
import sys
from PIL import Image, ImageOps
from bill_parser import parse_freight_bill, match_carrier
from db import get_connection  # reuses your existing db.py

# A "text layer" shorter than this for a full invoice page is almost
# certainly noise, not real text -> treat it as absent and OCR instead.
MIN_PLAUSIBLE_TEXT_LAYER_CHARS = 40


def _pdf_text_layer(pdf_path: str) -> str | None:
    """Try to pull real text straight out of a PDF. Returns None (not an
    empty string) if there's no usable layer, so the caller knows to fall
    back to OCR rather than silently trusting garbage."""
    try:
        import pypdf
        reader = pypdf.PdfReader(pdf_path)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return None
    if len(text.strip()) < MIN_PLAUSIBLE_TEXT_LAYER_CHARS:
        return None
    return text


def _ocr_image(image, config: str = "") -> str:
    """OCR one image (a file path or a PIL Image) with Tesseract."""
    import pytesseract

    return pytesseract.image_to_string(image, config=config)


def _preprocess_for_ocr(image):
    """Create a conservative OCR image without changing the source file.

    This is deliberately used only as a retry. The original pixels remain
    the first and preferred OCR input.
    """
    if isinstance(image, (str, bytes, os.PathLike)):
        image = Image.open(image)
    gray = ImageOps.grayscale(image)
    return gray.resize((gray.width * 2, gray.height * 2), Image.Resampling.LANCZOS)


def _ocr_pdf_pages(
    pdf_path: str,
    dpi: int = 200,
    preprocess: bool = False,
    config: str = "",
) -> str:
    """Only reached when the PDF has no usable text layer, i.e. it's
    actually a scanned image saved as a PDF. Renders each page to an
    image and OCRs it with Tesseract the same way a plain image would be."""
    from pdf2image import convert_from_path

    pages = convert_from_path(
        pdf_path,
        dpi=dpi,
        poppler_path=r"E:\poppler\poppler-26.07.0\Library\bin",
    )
    if preprocess:
        pages = [_preprocess_for_ocr(page_image) for page_image in pages]
    return "\n".join(_ocr_image(page_image, config=config) for page_image in pages)


def extract_raw_text(file_path: str) -> str:
    """Return the first-pass OCR text for an image or rendered PDF."""
    if file_path.lower().endswith(".pdf"):
        return _ocr_pdf_pages(file_path)

    return _ocr_image(file_path)


def _extract_ocr_candidates(file_path: str) -> list[tuple[str, str]]:
    """Return OCR attempts in risk order, keeping the original first."""
    if file_path.lower().endswith(".pdf"):
        return [
            (_ocr_pdf_pages(file_path, dpi=200), "pdf-200dpi"),
            (_ocr_pdf_pages(file_path, dpi=300), "pdf-300dpi"),
            (_ocr_pdf_pages(file_path, dpi=300, config="--psm 6"), "pdf-300dpi-psm6"),
            (_ocr_pdf_pages(file_path, dpi=300, config="--psm 11"), "pdf-300dpi-psm11"),
            (
                _ocr_pdf_pages(file_path, dpi=300, preprocess=True),
                "pdf-300dpi-enhanced",
            ),
        ]

    with Image.open(file_path) as image:
        return [
            (_ocr_image(image), "original"),
            (_ocr_image(_preprocess_for_ocr(image)), "enhanced"),
        ]


def get_known_carriers() -> list:
    """
    Pulls the real, current list of carriers straight from carrier_master -
    this is the "known short list" match_carrier() fuzzy-matches OCR text
    against. Never hand-typed, never hardcoded - always live from the DB,
    which itself comes from the TMS API sync.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT "carrierCode", "carrierName" FROM carrier_master')
            return cur.fetchall()
    finally:
        conn.close()


def get_valid_load_ids() -> set:
    """
    Pulls the real, current set of load IDs straight from the load table -
    same pattern as get_known_carriers(). Used to sanity-check each parsed
    line item's userReferenceNumber BEFORE attempting the database write,
    so a bad OCR digit-read (e.g. "706" instead of "7066") gets caught
    with a clear, specific warning instead of crashing the whole bill's
    insert with a raw foreign-key-violation error from Postgres.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT "systemLoadID" FROM load')
            return {row[0] for row in cur.fetchall()}
    finally:
        conn.close()


def bill_already_exists(carrier_code: str, freight_bill_number: str) -> bool:
    """
    Checks if this (carrier, bill number) pair is already in the database.

    IMPORTANT: identity is the PAIR, not freightBillNumber alone - two
    different carriers can issue bills with the same invoice number (this
    has actually happened: Safexpress and a non-carrier both used
    "FRHT-16"). Checking freightBillNumber alone would wrongly treat a
    genuinely different bill as a duplicate and silently drop it.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT 1 FROM freight_bill WHERE "carrierCode" = %s AND "freightBillNumber" = %s',
                (carrier_code, freight_bill_number),
            )
            return cur.fetchone() is not None
    finally:
        conn.close()


def _next_detail_id(cur) -> int:
    """
    freightBillDetailID is a plain integer primary key (not auto-generated),
    and the TMS API assigns its own IDs directly. To guarantee OCR-sourced
    rows never collide with API-sourced IDs, we start OCR IDs at 9,000,000 -
    comfortably above any realistic API-assigned ID range.
    """
    cur.execute(
        """SELECT COALESCE(MAX("freightBillDetailID"), 9000000) FROM freight_bill_details
           WHERE "freightBillDetailID" >= 9000000"""
    )
    current_max = cur.fetchone()[0]
    return current_max + 1


def _dates_equal(existing_date, new_date_str: str) -> bool:
    """
    Compares the DATE column's value (returned by psycopg2 as a native
    datetime.date object - NOT a string, and NOT affected by the server's
    datestyle setting) against parsed["invoiceDate"], which is now a
    DD-MM-YYYY string (see bill_parser.py's _parse_date).

    Since these are two different representations, we normalize existing_date
    to the same DD-MM-YYYY string format before comparing - a plain
    str(existing_date) would ALWAYS produce ISO (YYYY-MM-DD) regardless of
    datestyle, which would never match a DD-MM-YYYY string and would make
    every re-scan incorrectly look "changed."
    """
    if existing_date is None or not new_date_str:
        return False
    existing_str = existing_date.strftime("%d-%m-%Y")
    return existing_str == new_date_str


def upsert_freight_bill(parsed: dict) -> str:
    """
    Inserts a NEW (carrierCode, freightBillNumber) bill, or UPDATES it if
    that pair already exists - a genuine re-scan (e.g. a corrected bill)
    now overwrites the old data instead of being silently skipped.

    For an update: freight_bill's date/amount are updated directly.
    freight_bill_details' line items are fully replaced (old rows deleted,
    new ones inserted) rather than merged - since there's no reliable way
    to match "old line item 3" to "new line item 3" across two independent
    OCR passes, a clean replace is safer than trying to patch individual
    rows.

    NOTE: if discrepancy ever starts being populated, it holds a foreign
    key into freightBillDetailID - deleting detail rows referenced there
    would fail (or need explicit handling). Not an issue today since
    discrepancy is empty, but worth remembering if that changes.

    Requires parsed["carrierCode"] to already be set (by match_carrier()
    in ingest_bill_image, before this is called).

    Returns "inserted", "updated", or "unchanged" (existed, but new scan
    had identical date/amount - no write performed).

    NOTE ON DATES: parsed["invoiceDate"] is now a DD-MM-YYYY string (see
    bill_parser.py). This relies on the database's datestyle being set to
    'ISO, DMY' (via ALTER DATABASE ... SET datestyle) so that Postgres
    correctly interprets the DD-MM-YYYY string being sent in on INSERT/
    UPDATE. See _dates_equal() above for how the read-back comparison is
    handled, since psycopg2 always returns DATE columns as native
    datetime.date objects regardless of datestyle.
    """
    carrier_code = parsed["carrierCode"]
    bill_number = parsed["freightBillNumber"]

    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    'SELECT "invoiceDate", "freightAmount" FROM freight_bill '
                    'WHERE "carrierCode" = %s AND "freightBillNumber" = %s',
                    (carrier_code, bill_number),
                )
                existing = cur.fetchone()

                if existing is None:
                    # New bill - plain insert
                    cur.execute(
                        """
                        INSERT INTO freight_bill ("carrierCode", "freightBillNumber", "invoiceDate", "freightAmount")
                        VALUES (%s, %s, %s, %s)
                        """,
                        (carrier_code, bill_number, parsed["invoiceDate"], parsed["freightAmount"]),
                    )
                    _insert_details(cur, carrier_code, bill_number, parsed["details"])
                    return "inserted"

                existing_date, existing_amount = existing
                unchanged = (
                    _dates_equal(existing_date, parsed["invoiceDate"])
                    and existing_amount is not None
                    and abs(float(existing_amount) - parsed["freightAmount"]) < 0.01
                )
                if unchanged:
                    return "unchanged"

                # Re-scan with different values - update in place
                cur.execute(
                    """
                    UPDATE freight_bill SET "invoiceDate" = %s, "freightAmount" = %s
                    WHERE "carrierCode" = %s AND "freightBillNumber" = %s
                    """,
                    (parsed["invoiceDate"], parsed["freightAmount"], carrier_code, bill_number),
                )
                cur.execute(
                    'DELETE FROM freight_bill_details WHERE "carrierCode" = %s AND "freightBillNumber" = %s',
                    (carrier_code, bill_number),
                )
                _insert_details(cur, carrier_code, bill_number, parsed["details"])
                return "updated"
    finally:
        conn.close()


def _insert_details(cur, carrier_code: str, bill_number: str, details: list) -> None:
    """Shared by upsert_freight_bill for both the insert and update paths."""
    for detail in details:
        detail_id = _next_detail_id(cur)
        cur.execute(
            """
            INSERT INTO freight_bill_details
                ("freightBillDetailID", "carrierCode", "freightBillNumber",
                 "userReferenceNumber", "freightBillDetailTotal")
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                detail_id,
                carrier_code,
                bill_number,
                detail["userReferenceNumber"],
                detail["freightBillDetailTotal"],
            ),
        )


def ingest_bill_image(image_path: str, dry_run: bool = False) -> dict:
    """
    Full pipeline for one bill image.
    Set dry_run=True to see the parsed JSON without touching the database
    (useful while you're still tuning bill_parser.py against real samples).
    """
    print(f"[1/3] Running OCR on {image_path} ...")
    candidates = _extract_ocr_candidates(image_path)
    known_carriers = get_known_carriers()
    valid_load_ids = get_valid_load_ids()

    parsed = None
    bad_loads = []
    selected_source = candidates[0][1]
    best_score = -1
    for raw_text, source in candidates:
        candidate = parse_freight_bill(raw_text)
        carrier_match = match_carrier(raw_text, known_carriers)
        candidate["carrierCode"] = carrier_match["carrierCode"] if carrier_match else None
        candidate_bad_loads = [
            d["userReferenceNumber"]
            for d in candidate["details"]
            if d["userReferenceNumber"] not in valid_load_ids
        ]
        has_required_fields = all(
            candidate[key] is not None
            for key in ("freightBillNumber", "invoiceDate", "freightAmount")
        )
        if candidate["validated"] and not candidate_bad_loads and carrier_match and has_required_fields:
            parsed = candidate
            selected_source = source
            break
        score = (
            sum(candidate[key] is not None for key in
                ("freightBillNumber", "invoiceDate", "freightAmount"))
            + min(len(candidate["details"]), 20)
            + (10 if candidate["validated"] else 0)
            - len(candidate_bad_loads) * 5
        )
        if score > best_score:
            parsed = candidate
            best_score = score
            bad_loads = candidate_bad_loads
            selected_source = source

    if parsed is None:
        raise RuntimeError(f"No OCR result produced for {image_path}")

    if selected_source != candidates[0][1]:
        parsed["warnings"].append(
            f"Initial OCR failed validation; retry {selected_source} selected"
        )

    carrier_match = match_carrier(
        "\n".join(text for text, source in candidates if source == selected_source),
        known_carriers,
    )
    if carrier_match:
        parsed["carrierCode"] = carrier_match["carrierCode"]
        parsed["warnings"].append(
            f"Carrier matched: {carrier_match['carrierName']} "
            f"({carrier_match['carrierCode']}), confidence {carrier_match['score']:.2f}"
        )
    else:
        parsed["carrierCode"] = None
        parsed["warnings"].append(
            "Could not confidently match a known carrier (carrier_master) - "
            "bill NOT inserted. Either this carrier isn't registered yet, "
            "or OCR text quality is too poor to match. Review manually."
        )

    bad_loads = [
        d["userReferenceNumber"]
        for d in parsed["details"]
        if d["userReferenceNumber"] not in valid_load_ids
    ]
    missing_fields = [
        key for key in ("freightBillNumber", "invoiceDate", "freightAmount")
        if parsed[key] is None
    ]
    if missing_fields:
        parsed["warnings"].append(
            f"Required invoice fields missing: {', '.join(missing_fields)}"
        )
        parsed["validated"] = False
    if bad_loads:
        real_loads = sorted(valid_load_ids)
        lo, hi = (real_loads[0], real_loads[-1]) if real_loads else ("?", "?")
        parsed["warnings"].append(
            f"Load {', '.join(str(b) for b in bad_loads)} not found in load table "
            f"(real loads range {lo}-{hi}) - likely OCR digit-drop. "
            f"Bill NOT inserted, review manually."
        )
        parsed["validated"] = False

    if parsed["warnings"]:
        print("  WARNINGS:")
        for w in parsed["warnings"]:
            print(f"    - {w}")

    if not parsed["validated"]:
        print("  Skipping database insert - validation failed. Review manually.")
        return parsed

    if parsed["carrierCode"] is None:
        print("  Skipping database insert - no confident carrier match. Review manually.")
        parsed["validated"] = False  # so ocr_batch.py routes this to failed/, not processed/
        return parsed

    if dry_run:
        print("  Dry run - not inserting into database.")
        return parsed

    print("[3/3] Writing to database ...")
    outcome = upsert_freight_bill(parsed)
    if outcome == "inserted":
        print(f"  Done. {parsed['carrierCode']}/{parsed['freightBillNumber']} inserted "
              f"({len(parsed['details'])} line items, total {parsed['freightAmount']}).")
    elif outcome == "updated":
        print(f"  Done. {parsed['carrierCode']}/{parsed['freightBillNumber']} already existed - "
              f"UPDATED with new values ({len(parsed['details'])} line items, "
              f"total {parsed['freightAmount']}).")
    else:  # "unchanged"
        print(f"  {parsed['carrierCode']}/{parsed['freightBillNumber']} already exists with "
              f"identical values - nothing to update.")
    parsed["dbOutcome"] = outcome
    return parsed


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ocr_ingest.py path/to/bill.png [--dry-run]")
        sys.exit(1)

    image_path = sys.argv[1]
    dry_run = "--dry-run" in sys.argv
    ingest_bill_image(image_path, dry_run=dry_run)
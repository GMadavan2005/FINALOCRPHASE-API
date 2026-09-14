import re
import difflib
from datetime import datetime

# How confident a fuzzy match must be (0-1) before we trust it enough to
# auto-assign a carrierCode. Below this, we refuse to guess - see
# match_carrier() below.
CARRIER_MATCH_THRESHOLD = 0.75


def _clean_number(s: str) -> float:
    return float(s.replace(",", "").replace("$", "").strip())


def _parse_date(raw_date: str) -> str:
    raw_date = raw_date.strip()
    formats_to_try = [
        "%d. %m. %Y", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d",
        "%d/%m/%y", "%d.%m.%y", "%m/%d/%y",
    ]
    for fmt in formats_to_try:
        try:
            return datetime.strptime(raw_date, fmt).strftime("%d-%m-%Y")  # <-- changed
        except ValueError:
            continue
    return raw_date


_MONEY_RE = re.compile(r"^\$?([\d,]+\.\d{2})\$?$")


def parse_freight_bill(raw_text: str) -> dict:
    result = {
        "freightBillNumber": None,
        "invoiceDate": None,
        "freightAmount": None,
        "details": [],
        "validated": False,
        "warnings": [],
    }

    # Invoice number: covers "Invoice No.: FRHT-1" (Blue Dart, SAFEX) and
    # "INVOICE # FRHT-5" (DHLEX) - the marker before the number can be
    # "No.", "No", "Number", or "#".
    # Take the first match where the captured token actually contains a
    # digit - guards against boilerplate text like "please use the invoice
    # number as reference" (EKART's footer note) matching the marker and
    # grabbing an ordinary word ("as") as if it were the bill number. A
    # real invoice number always has a digit in it; plain English doesn't.
    m = None
    for candidate in re.finditer(r"Invoice\s*(?:No\.?|Number|#)\s*:?\s*([A-Za-z0-9\-_]+)", raw_text, re.IGNORECASE):
        if any(ch.isdigit() for ch in candidate.group(1)):
            m = candidate
            break
    if m:
        result["freightBillNumber"] = m.group(1).strip()
    else:
        # Fallback: EKART's "Invoice No." label sometimes gets OCR-mangled
        # into gibberish entirely (overlapping table cells), so there's no
        # usable label to anchor on. Every bill number in this system is
        # still shaped like LETTERS-DIGITS (e.g. FRHT-9), so as a last
        # resort grab the first token matching that shape. "Load 6918"
        # style line-item numbers are pure digits with no letter prefix,
        # so they can't collide with this.
        m = re.search(r"\b([A-Za-z]{2,8}-\d+)\b", raw_text)
        if m:
            result["freightBillNumber"] = m.group(1).strip()
            result["warnings"].append(
                f"Invoice number label unreadable (OCR garbled) - recovered '{m.group(1)}' "
                f"from document shape instead, please verify"
            )
        else:
            result["warnings"].append("Could not find invoice number")

    m = re.search(r"Issue\s*date:?\s*([\d./\s]+\d{4})", raw_text, re.IGNORECASE)
    if not m:
        m = re.search(r"Due\s*date:?\s*([\d./\s]+\d{4})", raw_text, re.IGNORECASE)
    if not m:
        # Fallback: DHLEX has no "Issue date"/"Due date" label at all - the
        # date just sits alone on its own line, right under the invoice
        # number. Grab the first bare date-shaped token in the document.
        m = re.search(r"\b(\d{1,2}[./]\s?\d{1,2}[./]\s?\d{2,4})\b", raw_text)
    if m:
        result["invoiceDate"] = _parse_date(m.group(1))
    else:
        result["warnings"].append("Could not find invoice date")

    # Total: covers "Total (NZD): 29,881.40 $" (Blue Dart/SAFEX, $ after
    # digits - already worked) AND "INVOICE TOTAL  $ 32,495.00" / "Total
    # (NZD): $41,665.00" (DHLEX/SAFEX, $ BEFORE digits - previously broke
    # the match entirely since $ isn't a digit).
    # Every candidate "Total"-labeled amount in the doc is collected and
    # the LAST one is used, since "Subtotal" also contains the substring
    # "Total" and appears before the real final total whenever fees exist -
    # taking the last match favors the final total over a subtotal.
    matches = list(re.finditer(
        r"Total\s*(?:\(?\w*\)?)?\s*(?:due)?\s*[:\(]?\s*\$?\s*([\d,]+\.\d{2})",
        raw_text,
        re.IGNORECASE,
    ))
    if matches:
        result["freightAmount"] = _clean_number(matches[-1].group(1))
    else:
        result["warnings"].append("Could not find total amount")

    # --- Line items: token-based, works whether OCR gives one long line
    # per load ("Load 6914 ... 1 533.40 533.40") or splits each field
    # onto its own line/list-item (real PaddleOCR output does this).
    # str.split() treats newlines the same as spaces, so both layouts
    # become the same flat token stream.
    tokens = raw_text.split()
    i = 0
    while i < len(tokens):
        if tokens[i].lower() == "load" and i + 1 < len(tokens):
            load_match = re.match(r"(\d+)", tokens[i + 1])
            if load_match:
                load_no = int(load_match.group(1))
                money_values = []
                j = i + 2
                lookahead_limit = min(j + 8, len(tokens))
                while j < lookahead_limit and tokens[j].lower() != "load":
                    mm = _MONEY_RE.match(tokens[j])
                    if mm:
                        money_values.append(_clean_number(mm.group(1)))
                        if len(money_values) >= 2:
                            j += 1
                            break
                    j += 1

                if len(money_values) >= 2:
                    result["details"].append(
                        {
                            "userReferenceNumber": load_no,
                            "freightBillDetailTotal": money_values[-1],
                        }
                    )
                elif len(money_values) == 1:
                    result["details"].append(
                        {
                            "userReferenceNumber": load_no,
                            "freightBillDetailTotal": money_values[0],
                        }
                    )
                    result["warnings"].append(
                        f"Load {load_no}: only one amount value found nearby - used it, please verify"
                    )
                else:
                    result["warnings"].append(
                        f"Load {load_no}: found 'Load' marker but no nearby amount - line item skipped"
                    )
                i = j
                continue
        i += 1

    if not result["details"]:
        result["warnings"].append("No line items matched - check layout/regex")

    if result["details"] and result["freightAmount"] is not None:
        line_sum = round(sum(d["freightBillDetailTotal"] for d in result["details"]), 2)
        stated_total = round(result["freightAmount"], 2)
        result["validated"] = abs(line_sum - stated_total) < 0.01
        if not result["validated"]:
            result["warnings"].append(
                f"Line items sum to {line_sum} but stated total is {stated_total} - FLAG FOR REVIEW"
            )

    return result


def match_carrier(raw_text: str, known_carriers: list) -> dict | None:
    """
    Tries to identify which carrier (from carrier_master) issued this bill,
    by fuzzy-matching the OCR'd text against the small, known list of real
    carrier names - NOT free-form fuzzy matching against arbitrary text.

    known_carriers: list of (carrierCode, carrierName) tuples, as pulled
    directly from carrier_master - e.g. [("BDTEX", "Bluedart Express"), ...]

    Returns {"carrierCode": ..., "carrierName": ..., "score": ...} for the
    best match IF it's confident enough (score >= CARRIER_MATCH_THRESHOLD).

    Returns None if nothing matched confidently - this is deliberate: a
    bill from a carrier that isn't in carrier_master (e.g. a one-off,
    unregistered carrier) must NOT be guessed at or auto-inserted with a
    wrong/made-up code. The caller should treat None as "flag for manual
    review, do not insert".
    """
    if not known_carriers:
        return None

    # Build candidate strings to compare against each known carrier name:
    # - every non-empty line of the OCR'd text
    # - short sliding windows of 2-3 consecutive tokens, so a name that got
    #   split across separate OCR list-items (e.g. "BLUE" / "DART" /
    #   "EXPRESS" as 3 separate rec_texts entries) still has a chance to
    #   line up against a multi-word carrier name like "Bluedart Express"
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    tokens = raw_text.split()
    candidates = set(lines)
    # window=1 added: some layouts (DHLEX, SAFEX) print only the short
    # carrierCode standalone (e.g. "DHLEX"), never the full descriptive
    # name nearby as its own clean phrase - a 2/3-word window pulls in an
    # unrelated neighboring word (e.g. "SAFEX AMAZON") and dilutes the score.
    for window in (1, 2, 3):
        for i in range(len(tokens) - window + 1):
            candidates.add(" ".join(tokens[i : i + window]))

    best = None
    for code, name in known_carriers:
        name_norm = name.strip().lower()
        code_norm = code.strip().lower()
        for cand in candidates:
            cand_norm = cand.strip().lower()
            # Score against BOTH the descriptive name ("DHL Express") and
            # the short carrierCode ("DHLEX") - whichever the OCR text
            # actually contains cleanly wins. This is what makes DHLEX/
            # SAFEX matchable at all, since their bills only ever print
            # the short code standalone, not the long name.
            score = max(
                difflib.SequenceMatcher(None, name_norm, cand_norm).ratio(),
                difflib.SequenceMatcher(None, code_norm, cand_norm).ratio(),
            )
            if best is None or score > best["score"]:
                best = {"carrierCode": code, "carrierName": name, "score": score}

    if best and best["score"] >= CARRIER_MATCH_THRESHOLD:
        return best
    return None
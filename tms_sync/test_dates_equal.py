"""
test_dates_equal.py
====================
Verifies _dates_equal() in ocr_ingest.py correctly compares:
  - existing_date: a native datetime.date object (what psycopg2 ALWAYS
    returns for a DATE column, regardless of datestyle setting)
  - new_date_str: a "DD-MM-YYYY" string (what bill_parser.py now produces)

Run:
    python test_dates_equal.py
"""

import sys
from datetime import date

sys.path.insert(0, ".")
from ocr_ingest import _dates_equal

test_cases = [
    # (existing_date as real date object, new_date_str, expected_result, meaning)
    (date(2025, 3, 5),  "05-03-2025", True,  "Same date, re-scan unchanged -> should match"),
    (date(2025, 3, 5),  "06-03-2025", False, "Different date -> should NOT match (genuine update)"),
    (date(2024, 12, 31), "31-12-2024", True, "Year-end date, unchanged"),
    (date(2025, 3, 5),  "03-05-2025", False, "Swapped day/month string -> correctly NOT equal (catches bugs)"),
    (None,              "05-03-2025", False, "No existing date on file -> not equal (safe default)"),
]

print("Testing _dates_equal() from ocr_ingest.py\n")

all_passed = True
for existing, new_str, expected, meaning in test_cases:
    result = _dates_equal(existing, new_str)
    passed = result == expected
    all_passed &= passed
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] existing={existing!r:15} new={new_str!r:15} -> got={result!r:6} expected={expected!r:6}  ({meaning})")

print()
if all_passed:
    print("All cases passed - re-scan 'unchanged' detection will work correctly with DMY strings.")
else:
    print("Some cases FAILED - send me this output.")
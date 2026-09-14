from bill_parser import parse_freight_bill
import json

# This simulates what Tesseract/PaddleOCR would output as raw text
# from the invoice image you shared.
sample_ocr_text = """
Invoice
Freight solutions, 126 Industry Road, Auckland 1060, New Zealand
BILL TO
BDTEX
75 Hamlin Road
Auckland 1060
New Zealand
Invoice No.: FRHT-1
Issue date: 30. 9. 2026
Due date: 30. 9. 2026
Reference: FT_PRE_PAID
Invoice No. FRHT-1
Issue date 30. 9. 2026
Due date 30. 9. 2026
Total due (NZD) 29,881.40 $
Description Quantity Unit price ($) Amount ($)
Freight shipping - Load 6914 1 533.40 533.40
Freight shipping - Load 6931 1 2,287.40 2,287.40
Freight shipping - Load 6937 1 2,412.80 2,412.80
Freight shipping - Load 6944 1 2,050.00 2,050.00
Freight shipping - Load 6947 1 2,702.00 2,702.00
Freight shipping - Load 6887 1 2,258.00 2,258.00
Freight shipping - Load 6891 1 2,258.00 2,258.00
Freight shipping - Load 6896 1 1,054.20 1,054.20
Freight shipping - Load 6901 1 1,790.40 1,790.40
Freight shipping - Load 6905 1 1,385.60 1,385.60
Freight shipping - Load 6953 1 1,507.80 1,507.80
Freight shipping - Load 6956 1 1,750.00 1,750.00
Freight shipping - Load 6958 1 2,124.20 2,124.20
Freight shipping - Load 6962 1 3,065.60 3,065.60
Freight shipping - Load 6974 1 2,702.00 2,702.00
Total (NZD): 29,881.40 $
"""

result = parse_freight_bill(sample_ocr_text)
print(json.dumps(result, indent=2))

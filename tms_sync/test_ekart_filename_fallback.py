import unittest

from bill_parser import parse_freight_bill


class EKARTFilenameFallbackTest(unittest.TestCase):
    def test_does_not_use_filename_when_ocr_invoice_label_is_missing(self):
        raw_text = """
        exart INVOICE
        LOGISTICS

        Name: EKART LOGISTICS
        Address: 12 Freight Drive
        Auckland 1060
        New Zealand

        Load 6902 3,456.00 3,456.00
        Load 6954 3,249.00 3,249.00
        Load 6957 2,983.00 2,983.00
        Load 6959 4,105.00 4,105.00
        Load 6965 4,892.00 4,892.00
        Load 6969 3,451.00 3,451.00
        Load 6975 4,231.00 4,231.00

        NOTES Subtotal (NZD) 26,367.00
        Balance Due (NZD) $26,367.00
        """

        parsed = parse_freight_bill(raw_text)
        self.assertIsNone(parsed['freightBillNumber'])
        self.assertEqual(parsed['freightAmount'], 26367.0)
        self.assertIn('Could not find invoice number', parsed['hardIssues'])


if __name__ == '__main__':
    unittest.main()

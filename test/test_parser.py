import unittest
from parser.content_parser import ContentParser

class TestParser(unittest.TestCase):
    def test_extract_order_info(self):
        parser = ContentParser()
        result = parser.extract_order_info("Sub", "Body", "PDF Text")
        self.assertIn("Sub", result["raw_combined_text"])
        self.assertIn("Body", result["raw_combined_text"])
        self.assertIn("PDF Text", result["raw_combined_text"])

if __name__ == '__main__':
    unittest.main()

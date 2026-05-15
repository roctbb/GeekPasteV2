import os
import tempfile
import unittest

from ai_detector import analyze_code_for_ai_usage


class AiDetectorSecurityTests(unittest.TestCase):
    def test_zip_payload_is_parsed_as_json_not_evaluated(self):
        marker_path = os.path.join(tempfile.gettempdir(), "geekpaste_eval_marker")
        try:
            os.remove(marker_path)
        except FileNotFoundError:
            pass

        payload = f"__import__('pathlib').Path({marker_path!r}).write_text('executed')"
        analyze_code_for_ai_usage(payload, "zip")

        self.assertFalse(os.path.exists(marker_path))


if __name__ == "__main__":
    unittest.main()

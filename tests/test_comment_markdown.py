from pathlib import Path
from types import SimpleNamespace
import unittest

from comment_markdown import render_comment_markdown
from methods import build_submission_status_payload


ROOT = Path(__file__).resolve().parents[1]


class CommentMarkdownTests(unittest.TestCase):
    def test_formats_gpt_comment_markdown(self):
        rendered = str(
            render_comment_markdown(
                "**Итог**: `count_even`\n\n1. Первый пункт\n2. Второй пункт"
            )
        )

        self.assertIn("<strong>Итог</strong>", rendered)
        self.assertIn("<code>count_even</code>", rendered)
        self.assertIn("<ol>", rendered)
        self.assertIn("<li>Первый пункт</li>", rendered)

    def test_removes_unsafe_html_and_link_protocols(self):
        rendered = str(
            render_comment_markdown(
                '<script>alert(1)</script><img src=x onerror="alert(2)"> '
                '[опасная ссылка](javascript:alert(3))'
            )
        )

        self.assertNotIn("<script", rendered)
        self.assertNotIn("<img", rendered)
        self.assertNotIn("onerror", rendered)
        self.assertNotIn("javascript:", rendered)

    def test_status_payload_contains_html_only_for_non_test_checkers(self):
        gpt_code = SimpleNamespace(
            id="ABC123",
            check_state="partially done",
            check_points=5,
            check_comments="**Почти** готово",
            checked_at=None,
            task=SimpleNamespace(check_type="gpt"),
        )
        test_code = SimpleNamespace(
            id="DEF456",
            check_state="partially done",
            check_points=5,
            check_comments="**Почти** готово",
            checked_at=None,
            task=SimpleNamespace(check_type="tests"),
        )

        gpt_payload = build_submission_status_payload(gpt_code)
        test_payload = build_submission_status_payload(test_code)

        self.assertIn("<strong>Почти</strong>", gpt_payload["check_comments_html"])
        self.assertNotIn("check_comments_html", test_payload)

    def test_initial_page_render_uses_the_complete_status_payload(self):
        template = (ROOT / "templates" / "code.html").read_text(encoding="utf-8")

        self.assertIn(
            "renderSubmissionStatus({{ submission_status | tojson }}, false);",
            template,
        )
        self.assertIn(
            "submission_status.get('check_comments_html', '') | safe",
            template,
        )


if __name__ == "__main__":
    unittest.main()

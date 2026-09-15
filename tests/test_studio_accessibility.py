"""Static checks for the studio's native dialogs (no browser or service needed)."""
from html.parser import HTMLParser
from pathlib import Path
import unittest


class Elements(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.elements = []
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class StudioAccessibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).resolve().parents[1] / "launchloom/web/index.html"
        cls.elements = Elements(source.read_text(encoding="utf-8")).elements
        cls.by_id = {attrs["id"]: (tag, attrs) for tag, attrs in cls.elements if "id" in attrs}

    def test_dialog_names_reference_headings(self):
        dialogs = [attrs for tag, attrs in self.elements if tag == "dialog"]
        self.assertEqual(len(dialogs), 4)
        for dialog in dialogs:
            with self.subTest(dialog=dialog["id"]):
                heading = dialog["aria-labelledby"]
                self.assertEqual(self.by_id[heading][0], "h2")

    def test_ids_remain_unique(self):
        ids = [attrs["id"] for _, attrs in self.elements if "id" in attrs]
        self.assertEqual(len(ids), len(set(ids)))

    def test_close_buttons_have_names_and_do_not_submit(self):
        buttons = [attrs for tag, attrs in self.elements if tag == "button" and "data-close" in attrs]
        self.assertEqual(len(buttons), 3)
        for button in buttons:
            with self.subTest(dialog=button["data-close"]):
                self.assertEqual(button["type"], "button")
                self.assertTrue(button.get("aria-label"))
                self.assertEqual(self.by_id[button["data-close"]][0], "dialog")

    def test_form_errors_are_live_regions(self):
        for error_id in ("access-error", "create-error"):
            with self.subTest(error=error_id):
                attrs = self.by_id[error_id][1]
                self.assertEqual(attrs["role"], "alert")
                self.assertEqual(attrs["aria-atomic"], "true")

    def test_access_input_explains_local_key_and_errors(self):
        attrs = self.by_id["access-token"][1]
        self.assertEqual(attrs["type"], "password")
        self.assertIn("required", attrs)
        self.assertEqual(attrs["aria-describedby"].split(), ["access-help", "access-error"])
        for reference in attrs["aria-describedby"].split():
            self.assertIn(reference, self.by_id)

    def test_review_and_consent_defaults_are_unchanged(self):
        inputs = {attrs["name"]: attrs for tag, attrs in self.elements if tag == "input" and "name" in attrs}
        self.assertIn("required", inputs["claims_confirmed"])
        self.assertIn("checked", inputs["review_plan"])
        for name in ("allow_site_writes", "external_data_consent", "staging_confirmed", "media_rights"):
            with self.subTest(name=name):
                self.assertNotIn("checked", inputs[name])


if __name__ == "__main__":
    unittest.main()

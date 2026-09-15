import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location("post_copy", Path(__file__).resolve().parents[1] / "launchloom/post_copy.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class PostCopyTests(unittest.TestCase):
    def args(self, language="en"):
        return dict(name="Example", tagline="Recorded work", audience="makers", features=[("Export clips", "Choose a recorded clip"), ("Review copy", "Review the words before export")], language=language)

    def test_seven_channels_have_different_bodies_in_both_languages(self):
        for language in ["ja", "en"]:
            outputs = [module.compose_post_copy(**self.args(language), channel=c) for c in ["x", "bluesky", "threads", "linkedin", "youtube", "instagram", "tiktok"]]
            self.assertEqual(len(set(outputs)), 7)
            self.assertTrue(all("Example" in text and "Export clips" in text for text in outputs))

    def test_only_public_fields_are_accepted(self):
        with self.assertRaises(TypeError):
            module.compose_post_copy(**self.args(), channel="x", evidence="private note")

    def test_empty_features_and_unknown_inputs_fail_clearly(self):
        args = self.args(); args["features"] = []
        with self.assertRaises(ValueError): module.compose_post_copy(**args, channel="x")
        with self.assertRaises(ValueError): module.compose_post_copy(**self.args(), channel="unknown")
        with self.assertRaises(ValueError): module.compose_post_copy(**self.args("fr"), channel="x")

    def test_long_drafts_keep_the_complete_url(self):
        url = "https://example.org/?utm_source=bluesky"
        content = module.fit_post("日本語の長い紹介文" * 100, url, 300, len)
        self.assertLessEqual(len(content), 300)
        self.assertTrue(content.endswith(url)); self.assertIn("…", content)

    def test_preflight_uses_the_supplied_counter(self):
        measured = lambda text: sum(2 if ord(c) > 127 else 1 for c in text)
        result = module.fit_post("説明" * 300, "https://example.org/", 280, measured)
        self.assertLessEqual(measured(result), 280)

    def test_an_oversized_url_is_not_silently_reported_as_fitting(self):
        with self.assertRaises(ValueError): module.fit_post("Body", "https://example.org/" + "x" * 400, 300, len)

    def test_short_and_no_url_posts_are_unchanged(self):
        self.assertEqual(module.fit_post("body", "", 280, len), "body")
        self.assertEqual(module.fit_post("body", "https://example.org", 280, len), "body\n\nhttps://example.org")

    def test_make_posts_filters_private_and_unapproved_fields(self):
        from launchloom.models import Brief
        from launchloom.planning import make_posts, x_weight
        brief = Brief(name="Example", tagline="Recorded work", audience="makers", language="en", product_url="https://example.org/", channels=["x", "bluesky", "threads", "linkedin", "youtube", "instagram", "tiktok"], features=[{"title":"Export clips","detail":"Choose a recorded clip","approved":True,"evidence":"PRIVATE-EVIDENCE-NOTE"},{"title":"UNAPPROVED-CAPABILITY","detail":"UNAPPROVED-DETAIL","approved":False}])
        posts = make_posts(brief, "unit-test")
        self.assertEqual(len(posts), 7)
        for post in posts:
            self.assertEqual(post["state"], "draft")
            self.assertNotIn("PRIVATE-EVIDENCE", post["content"])
            self.assertNotIn("UNAPPROVED", post["content"])
            self.assertTrue(post["content"].endswith(post["utm_url"]))
        self.assertLessEqual(x_weight(posts[0]["content"]), 280)
        self.assertLessEqual(len(posts[1]["content"]), 300)

if __name__ == "__main__": unittest.main()

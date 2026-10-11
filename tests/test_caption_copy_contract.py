"""Static JA/EN copy contract for the standard studio's separate SRT captions.

Run with: python -m unittest discover -s tests -p test_caption_copy_contract.py -v
These checks do not render video or substitute for browser verification.
"""
from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
BOUNDARY_JA = (
    "見出し・補足は動画のレイアウトに、字幕は別ファイルのSRTにのみ反映されます。"
    "字幕の焼き込みや取込映像内の文字の変更はできません。"
    "LP・SNS原稿は最初の企画から作成します。"
)
BOUNDARY_EN = (
    "Headlines and supporting text change the video layout. "
    "Captions update the separate SRT only; they are not burned into the video. "
    "Text already in imported footage cannot be edited here. "
    "The page and social drafts use the original brief."
)
COPY = {
    BOUNDARY_JA: BOUNDARY_EN,
    "動画と字幕の文言を確認": "Review film and caption wording",
    "見出し・補足は動画用、字幕は別ファイルのSRT用です。取込映像内の文字は変更できません。確認したら、動画を作成してください。":
        "Headlines and supporting text appear in the video; captions are exported as a separate SRT. Text already in imported footage cannot be edited here. Review them, then create the films.",
    "まずは内蔵のOrbitサンプルで、字幕（SRT）をひとつ直して書き出してみましょう。":
        "Start with the bundled Orbit sample. Edit one SRT caption, then export it.",
    "構成と字幕（SRT）を編集・保存": "Edit and save the storyboard and SRT captions",
    "横長・縦長の動画、LP、SNS原稿、字幕（SRT）をZIPにまとめました。動画とSRTを確認してください。":
        "The ZIP contains landscape and portrait films, a page, social drafts and separate SRT captions. Review the films and SRT.",
    "字幕（SRT）": "Caption (SRT)",
}
DOCS = ("README.md", "README.ja.md", "docs/FIRST_PROOF.md", "docs/COMPATIBILITY.md")
JS_STRING = r"'(?:\\.|[^'\\])*'"


def function_source(source: str, name: str) -> str:
    """Isolate a top-level app function without executing browser code."""
    body = source.split(f"function {name}(", 1)[1]
    return re.split(r"\n(?:async )?function ", body, maxsplit=1)[0]


class CaptionCopyContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = (ROOT / "launchloom/web/app.js").read_text(encoding="utf-8")
        cls.i18n = (ROOT / "launchloom/web/i18n.js").read_text(encoding="utf-8")
        table = cls.i18n.split("const EN = {", 1)[1].split("\n};", 1)[0]
        entries = re.findall(
            rf"^\s*({JS_STRING}):\s*({JS_STRING})\s*,?\s*$", table, re.MULTILINE
        )
        cls.entries = [(ast.literal_eval(key), ast.literal_eval(value)) for key, value in entries]
        cls.table_key_count = len(re.findall(rf"^\s*{JS_STRING}:\s*", table, re.MULTILINE))
        cls.translations = dict(cls.entries)

    def test_translation_table_has_no_duplicate_exact_or_normalized_keys(self):
        self.assertEqual(len(self.entries), self.table_key_count, "Parse every EN table entry")
        # Match the DOM translator's normalization, including &nbsp; aliases.
        keys = [key.replace("&nbsp;", " ").replace("\u00a0", " ").strip() for key, _ in self.entries]
        duplicates = [key for key, count in Counter(keys).items() if count > 1]
        self.assertEqual(duplicates, [])

    def test_scope_copy_has_exact_english_translations_and_real_app_text_nodes(self):
        for japanese, english in COPY.items():
            with self.subTest(copy=japanese):
                self.assertEqual(self.translations.get(japanese), english)
                # A substring in a longer sentence is not a translatable DOM key.
                self.assertRegex(self.app, rf">\s*{re.escape(japanese)}\s*<")

    def test_review_result_and_revision_all_disclose_the_same_scope(self):
        for name in ("renderReview", "resultSummary", "renderRevise"):
            with self.subTest(function=name):
                self.assertIn(f'<p class="notice">{BOUNDARY_JA}</p>', function_source(self.app, name))

    def test_review_explains_imported_footage_before_any_collapsed_details(self):
        review_intro = function_source(self.app, "renderReview").split("${storyboardForm", 1)[0]
        self.assertNotIn("<details", review_intro)
        self.assertIn("取込映像内の文字は変更できません。", review_intro)
        intro_copy = next(key for key in COPY if key.startswith("見出し・補足は動画用"))
        self.assertIn(intro_copy, review_intro)
        self.assertIn("Text already in imported footage cannot be edited here.", self.translations[intro_copy])

    def test_caption_field_names_srt_and_keeps_headline_fallback(self):
        fields = function_source(self.app, "sceneFields")
        self.assertIn('<label>字幕（SRT） <small>空欄なら見出しを使います</small>', fields)
        self.assertEqual(self.translations["空欄なら見出しを使います"], "Empty means use the headline")
        self.assertNotIn("字幕", self.translations, "Do not leave the replaced caption label orphaned")

    def test_docs_explain_video_srt_imported_footage_and_original_brief(self):
        for relative in DOCS:
            text = " ".join((ROOT / relative).read_text(encoding="utf-8").split())
            with self.subTest(document=relative):
                self.assertIn("captions.srt", text)
                if relative == "README.ja.md":
                    for fragment in (
                        "見出し・補足を動画のレイアウトに反映",
                        "字幕は別ファイルの `captions.srt` にのみ反映",
                        "MP4には焼き込まれません",
                        "取込映像内にすでにある文字は変更できません",
                        "LP・SNS原稿は元の企画から作ります",
                    ):
                        self.assertIn(fragment, text)
                else:
                    for fragment in (
                        "headlines and supporting text change the video layout",
                        "separate `captions.srt`",
                        "not burned into the MP4",
                        "Text already inside imported footage cannot be edited here",
                        "original brief",
                    ):
                        self.assertIn(fragment, text)

    def test_superseded_misleading_copy_is_removed(self):
        sources = [self.app, self.i18n, *((ROOT / path).read_text(encoding="utf-8") for path in DOCS)]
        combined = " ".join(" ".join(source.split()) for source in sources)
        for obsolete in (
            "この画面の見出し・字幕の編集は映像に反映されます。",
            "Headline and caption edits here change the film.",
            "Headline/caption edits in the standard studio affect the film",
            "通常スタジオの見出し・字幕編集は映像に反映され",
            "standard studio changes film/captions from scene edits",
            "Legacy scene edits change film/captions",
            "承認すると、その文言のままレンダリングされます。",
            "画面上のシーン見出し。音声の文字起こしではない",
        ):
            with self.subTest(obsolete=obsolete):
                self.assertNotIn(obsolete, combined)


if __name__ == "__main__":
    unittest.main()

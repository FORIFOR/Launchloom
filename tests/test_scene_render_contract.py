"""Real frame regressions; no browser, model, network or encoded-video fixture."""
import hashlib
import unittest

from launchloom.models import Brief, PlanEdit
from launchloom.planning import make_plan, apply_plan_edit
from launchloom.models import Plan
from launchloom.rendering import render_frame


class SceneRenderContractTests(unittest.TestCase):
    def setUp(self):
        self.brief = Brief(name='Local demo', tagline='Original opening',
            audience='Original audience', language='en', features=[{
                'title': 'One real feature', 'detail': 'A bounded local example.',
                'evidence': 'Synthetic regression fixture only.', 'approved': True}])
        self.plan = make_plan(self.brief)

    def frame(self, plan, width, height, when, style='editorial'):
        pixels = render_frame(self.brief, plan, width, height, when, 20,
                              None, [], visual_style=style).tobytes()
        # Keep a regression failure readable instead of printing megabytes of RGB.
        return hashlib.sha256(pixels).hexdigest()

    def edited(self, **fields):
        change = PlanEdit(scenes=[{'index': 0, **fields}])
        return Plan.model_validate(apply_plan_edit(self.plan.model_dump(), change))

    def test_opening_title_and_detail_edits_reach_rendered_pixels(self):
        for dimensions in [(640, 360), (360, 640)]:
            for style in ['editorial', 'spotlight', 'grid']:
                for fields in [{'title': 'Revised opening'}, {'detail': 'Revised audience'}]:
                    with self.subTest(dimensions=dimensions, style=style, fields=fields):
                        self.assertNotEqual(
                            self.frame(self.plan, *dimensions, 1, style),
                            self.frame(self.edited(**fields), *dimensions, 1, style))

    def test_opening_edits_do_not_replace_proof_or_closing_words(self):
        changed = self.edited(title='Revised opening', detail='Revised audience')
        for dimensions in [(640, 360), (360, 640)]:
            for when in [8, 24]:
                with self.subTest(dimensions=dimensions, when=when):
                    self.assertEqual(self.frame(self.plan, *dimensions, when),
                                     self.frame(changed, *dimensions, when))

    def test_caption_field_is_sidecar_not_burnt_into_frames(self):
        changed = self.plan.model_copy(deep=True)
        for index, scene in enumerate(changed.scenes):
            scene.caption = 'Separate SRT caption ' + str(index)
        for dimensions in [(640, 360), (360, 640)]:
            for when in [1, 8, 24]:
                with self.subTest(dimensions=dimensions, when=when):
                    self.assertEqual(self.frame(self.plan, *dimensions, when),
                                     self.frame(changed, *dimensions, when))

    def test_unedited_opening_keeps_brief_wording(self):
        self.assertEqual(self.plan.scenes[0].title, self.brief.tagline)
        self.assertEqual(self.plan.scenes[0].detail, self.brief.audience)


if __name__ == '__main__':
    unittest.main()

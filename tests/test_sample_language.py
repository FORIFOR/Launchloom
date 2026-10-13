"""The bundled capture's operation labels follow the brief, including on retry."""
import asyncio
import copy
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from PIL import Image

from launchloom import pipeline, rendering
from launchloom.config import Settings
from launchloom.models import Brief, BuildOptions, CaptureEvent, CaptureStep
from launchloom.planning import make_plan
from launchloom.store import Store

capture = importlib.import_module('launchloom.capture')
JA = tuple(step.label for step in capture.SAMPLE_STEPS)
EN = (
    'Capture the idea while it is fresh.',
    'Keep everything in one place.',
    'See what you have finished.',
    'Focus on the next step.',
)


def event_track(labels=JA):
    return [dict(time=float(i), label=label, action=step.action, x=.4, y=.3)
            for i, (step, label) in enumerate(zip(capture.SAMPLE_STEPS, labels))]


class SampleLanguageTests(unittest.TestCase):
    def test_both_languages_and_fallbacks_are_idempotent(self):
        for source in (JA, EN):
            for language, expected in (('en', EN), ('ja', JA), ('xx', JA), ('', JA)):
                with self.subTest(source=source, language=language):
                    events = event_track(source)
                    before = copy.deepcopy(events)
                    actual = capture.sample_events(events, language)
                    self.assertEqual(tuple(e['label'] for e in actual), expected)
                    self.assertEqual(capture.sample_events(actual, language), actual)
                    self.assertEqual(events, before)
                    for old, new in zip(events, actual):
                        self.assertIsNot(old, new)
                        self.assertEqual({k: v for k, v in old.items() if k != 'label'},
                                         {k: v for k, v in new.items() if k != 'label'})
        self.assertEqual(capture.sample_events(event_track()), event_track())
        self.assertEqual(tuple(step.label for step in capture.SAMPLE_STEPS), JA)

    def test_custom_empty_and_missing_labels_are_preserved(self):
        events = [dict(time=1, label='利用者が書いた説明'), dict(time=2, label=''), dict(time=3)]
        before = copy.deepcopy(events)
        for language in ('en', 'ja', 'xx'):
            self.assertEqual(capture.sample_events(events, language), before)
        self.assertEqual(events, before)

    def test_portrait_draws_each_localized_label_in_every_style(self):
        # Real Pillow frame rendering with synthetic footage/timing, not an MP4 test.
        raw = Image.new('RGB', (1280, 800), '#ccddee')
        for language, expected in (('en', EN), ('ja', JA)):
            brief = Brief.model_validate(pipeline.SAMPLES[language])
            plan = make_plan(brief)
            for style in rendering.STYLES:
                for index, event in enumerate(capture.sample_events(event_track(), language)):
                    with self.subTest(language=language, style=style, event=index):
                        event = {**event, 'time': 0.0}
                        with patch.object(rendering, 'wrapped', wraps=rendering.wrapped) as wrapped:
                            frame = rendering.render_frame(brief, plan, 720, 1280, 5.0, 12,
                                                           raw, [event], None, style)
                        drawn = [call.args[1] for call in wrapped.call_args_list]
                        self.assertEqual(frame.size, (720, 1280))
                        self.assertIn(expected[index], drawn)
                        other = JA if language == 'en' else EN
                        self.assertFalse(any(label in drawn for label in other))

    def test_empty_event_track_keeps_headline_fallback_without_duplication(self):
        brief = Brief.model_validate(pipeline.SAMPLES['en'])
        plan = make_plan(brief)
        with patch.object(rendering, 'wrapped', wraps=rendering.wrapped) as wrapped:
            rendering.render_frame(brief, plan, 720, 1280, 5.0, 12, None,
                                   capture.sample_events([], 'en'))
        drawn = [call.args[1] for call in wrapped.call_args_list]
        self.assertEqual(drawn.count(plan.scenes[1].title), 1)


class RenderReached(Exception):
    """Stop after observing the real pipeline's render inputs."""


class SampleLanguagePipelineTests(unittest.TestCase):
    def check_pipeline(self, language, mode, cached=False, capture_start=0.0):
        events = event_track() + [dict(time=5.0, label='custom wording', action='click', x=.2, y=.6)]
        before = copy.deepcopy(events)
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(data_dir=Path(directory), token='sample-language-test-token-long-enough')
            store = Store(settings.data_dir / 'test.sqlite3')
            campaign = store.create_campaign(copy.deepcopy(pipeline.SAMPLES[language]))
            root = settings.data_dir / 'campaigns' / campaign['id']
            root.mkdir(parents=True)
            kwargs = dict(capture_mode=mode, capture_start=capture_start)
            if mode == 'url':
                kwargs.update(capture_url='https://staging.example.test', staging_confirmed=True,
                              steps=[CaptureStep(action='click', selector='#done', label=JA[0])])
            elif mode == 'upload':
                kwargs['capture_events'] = [CaptureEvent.model_validate(e) for e in events]
                (root / 'input').mkdir()
                (root / 'input/capture.bin').write_bytes(b'test-double')
            options = BuildOptions(**kwargs)
            options_before = options.model_dump()
            if cached:
                (root / 'capture').mkdir()
                (root / 'capture/capture.webm').write_bytes(b'test-double')
                (root / 'capture/events.json').write_text(json.dumps({'events': events}))
                cached_bytes = (root / 'capture/events.json').read_bytes()
            capture_mock = AsyncMock(return_value={'events': events})
            with patch.object(pipeline, 'capture', capture_mock), \
                    patch.object(pipeline, 'build_site'), \
                    patch.object(pipeline, 'validate_media'), \
                    patch.object(pipeline, 'render', side_effect=RenderReached) as render:
                with self.assertRaises(RenderReached):
                    asyncio.run(pipeline.build(settings, store, campaign['id'], options))
            actual = render.call_args.args[4]
            expected = [*EN, 'custom wording'] if mode == 'sample' and language == 'en' else [e['label'] for e in before]
            self.assertEqual([e['label'] for e in actual], expected)
            self.assertEqual(events, before)
            self.assertEqual(options.model_dump(), options_before)
            for old, new in zip(before, actual):
                expected_event = {**old, 'time': old['time'] - capture_start}
                self.assertEqual({k: v for k, v in expected_event.items() if k != 'label'},
                                 {k: v for k, v in new.items() if k != 'label'})
            if cached:
                capture_mock.assert_not_awaited()
                self.assertEqual((root / 'capture/events.json').read_bytes(), cached_bytes)
            elif mode == 'upload':
                capture_mock.assert_not_awaited()
            else:
                capture_mock.assert_awaited_once()

    def test_fresh_and_cached_samples_follow_both_languages(self):
        for language in ('ja', 'en'):
            for cached in (False, True):
                with self.subTest(language=language, cached=cached):
                    self.check_pipeline(language, 'sample', cached)

    def test_url_script_labels_are_unchanged_even_when_matching_sample_text(self):
        for language in ('ja', 'en'):
            for cached in (False, True):
                with self.subTest(language=language, cached=cached):
                    self.check_pipeline(language, 'url', cached)

    def test_trimmed_samples_shift_event_times_once(self):
        for cached in (False, True):
            with self.subTest(cached=cached):
                self.check_pipeline('en', 'sample', cached, capture_start=1.25)

    def test_uploaded_labels_are_unchanged_even_when_matching_sample_text(self):
        for language in ('ja', 'en'):
            with self.subTest(language=language):
                self.check_pipeline(language, 'upload')


if __name__ == '__main__':
    unittest.main()

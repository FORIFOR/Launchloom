from pathlib import Path
import tempfile
import unittest
from homepage.publish_post_samples import render_page, publish, CHANNELS

PAGE = '<main>KEEP<video src="film.mp4"></video><ul class="drafts"><li>old</li></ul><template data-caption="posts">Old caption</template><form>CONSENT</form></main>'
def drafts():
    return [{'channel': ch, 'state': 'draft', 'content': f'{ch} <script>sample</script> & detail'} for ch in sorted(CHANNELS)]

class PublishPostSamplesTests(unittest.TestCase):
    def test_escapes_content_without_changing_media_or_forms(self):
        result = render_page(PAGE, drafts(), 'ja')
        self.assertEqual(result.count('<li>'), 7)
        self.assertIn('&lt;script&gt;', result)
        self.assertNotIn('<script>', result)
        self.assertIn('<video src="film.mp4"></video>', result)
        self.assertIn('<form>CONSENT</form>', result)
        self.assertIn('未投稿', result)
    def test_render_is_idempotent(self):
        once = render_page(PAGE, drafts(), 'en')
        self.assertEqual(render_page(once, drafts(), 'en'), once)
    def test_refuses_changed_page_structure(self):
        for page in [PAGE.replace('class="drafts"', 'class="other"'), PAGE + PAGE, PAGE.replace('data-caption="posts"', 'data-caption="other"')]:
            with self.assertRaises(ValueError): render_page(page, drafts(), 'en')
    def test_refuses_published_or_duplicate_or_missing_drafts(self):
        for items in [drafts()[:6], [dict(d, state='published') for d in drafts()], [dict(d, content='same') for d in drafts()]]:
            with self.assertRaises(ValueError): render_page(PAGE, items, 'ja')
    def test_second_invalid_page_leaves_first_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root/'ja').mkdir()
            (root/'index.html').write_text(PAGE); (root/'ja/index.html').write_text('wrong')
            with self.assertRaises(ValueError): publish(root, {'ja': drafts(), 'en': drafts()})
            self.assertEqual((root/'index.html').read_text(), PAGE)
            self.assertFalse((root/'post-drafts.json').exists())
    def test_only_three_paths_are_updated(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root/'ja').mkdir()
            for p in ['index.html', 'ja/index.html']: (root/p).write_text(PAGE)
            (root/'film.mp4').write_bytes(b'unchanged')
            changed = publish(root, {'ja': drafts(), 'en': drafts()})
            self.assertEqual({str(p.relative_to(root)) for p in changed}, {'index.html', 'ja/index.html', 'post-drafts.json'})
            self.assertEqual((root/'film.mp4').read_bytes(), b'unchanged')

if __name__ == '__main__': unittest.main()

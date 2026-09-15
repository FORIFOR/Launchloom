from html.parser import HTMLParser
from pathlib import Path
import ast
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class InlineScripts(HTMLParser):
    def __init__(self):
        super().__init__(); self.active=False; self.parts=[]
    def handle_starttag(self, tag, attrs):
        if tag=='script':
            self.active=not dict(attrs).get('src')
    def handle_endtag(self, tag):
        if tag=='script': self.active=False
    def handle_data(self, data):
        if self.active:self.parts.append(data)

class DesignStudiesTests(unittest.TestCase):
    def test_all_six_are_explicit_design_previews(self):
        source=(ROOT/'design-studies/index.html').read_text(encoding='utf-8')
        for product in ['genie','ai-meeting','oathra','aisecure','agent-team','launchloom']:
            self.assertIn("'"+product+"':",source)
        self.assertIn('NOT A LIVE PRODUCT DEMO',source)
        self.assertIn('サンプルデータ',source)
        self.assertIn('実装済み機能の証明ではありません',source)
        self.assertNotIn('getUserMedia',source)
        self.assertNotIn('fetch(',source)

    @unittest.skipUnless(shutil.which('node'),'Node is not installed')
    def test_embedded_javascript_parses(self):
        parsed=InlineScripts();parsed.feed((ROOT/'design-studies/index.html').read_text(encoding='utf-8'))
        self.assertTrue(parsed.parts)
        with tempfile.TemporaryDirectory() as folder:
            script=Path(folder)/'motion.js';script.write_text('\n'.join(parsed.parts),encoding='utf-8')
            subprocess.run(['node','--check',str(script)],check=True,capture_output=True,text=True)

    def test_renderer_and_sample_utility_are_valid_python(self):
        for path in ['design-studies/render.py','homepage/refresh_post_samples.py']:
            ast.parse((ROOT/path).read_text(encoding='utf-8'))

    def test_publication_adds_design_only_without_force_push(self):
        workflow=(ROOT/'.github/workflows/design-studies.yml').read_text(encoding='utf-8')
        self.assertIn('git add -- design',workflow)
        self.assertIn("grep -v '^design/'",workflow)
        self.assertIn('git push origin HEAD:gh-pages',workflow)
        self.assertNotIn('--force',workflow)
        self.assertNotIn('secrets.',workflow)

if __name__=='__main__':unittest.main()

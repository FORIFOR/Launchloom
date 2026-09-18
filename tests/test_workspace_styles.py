from hashlib import sha1
from pathlib import Path
import unittest
from fastapi.testclient import TestClient
from launchloom.config import Settings
from launchloom.server import create_app
import tempfile

WEB=Path(__file__).resolve().parents[1]/'launchloom/web'
class WorkspaceStyleTests(unittest.TestCase):
    def test_complete_prior_styles_preserved(self):
        data=(WEB/'app-base.css').read_bytes()
        self.assertEqual(sha1(f'blob {len(data)}\0'.encode()+data).hexdigest(),'4cf56ef2488fa51808653c97d3f78ccb44a5a9c1')
    def test_only_local_layers_are_imported(self):
        css=(WEB/'app.css').read_text()
        self.assertIn("'./app-base.css'",css);self.assertIn("'./workspace.css'",css)
        self.assertNotIn('https:',css)
    def test_actual_static_mount_serves_all_layers_without_auth_bypass(self):
        with tempfile.TemporaryDirectory() as d:
            with TestClient(create_app(Settings(data_dir=Path(d),token='x'*32),run_worker=False)) as client:
                for name in ['app.css','app-base.css','workspace.css']:
                    response=client.get('/static/'+name)
                    self.assertEqual(response.status_code,200)
                    self.assertIn('text/css',response.headers['content-type'])
                self.assertEqual(client.get('/api/campaigns').status_code,401)
    def test_state_and_consent_controls_remain_in_source(self):
        html=(WEB/'index.html').read_text();css=(WEB/'workspace.css').read_text()
        for field in ['claims_confirmed','review_plan','external_data_consent','allow_site_writes']:
            self.assertIn('name="'+field+'"',html)
        self.assertIn('[hidden]{display:none!important}',css)
        self.assertIn('prefers-reduced-motion',css)

if __name__=='__main__':unittest.main()

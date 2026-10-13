"""Isolated Chromium UI regression with mocked backend/transport, never a real upload.
Requires Python Playwright and its Chromium (or CHROMIUM_EXECUTABLE).
Run: python tests/test_final_film_recovery.py
"""
from pathlib import Path
import json
import os
import unittest
from playwright.sync_api import sync_playwright

SOURCE = Path(__file__).resolve().parents[1] / 'launchloom/web/final-films.js'
HTML = '<!doctype html><html lang="ja"><meta charset="utf-8"><main id="root"></main></html>'
MOCK_TRANSPORT = """() => {
window.posts=0; window.mode='success'; window.gets=0; window.failGetAt=[]; window.items=[];
window.fetch=async (url, options={})=>{
 if(options.method && options.method!=='GET')throw new Error('Only GET is allowed in this fixture');
 window.gets++;
 return {ok:!window.failGetAt.includes(window.gets),json:async()=>({items:window.items})};
};
window.XMLHttpRequest=class {
 constructor(){this.upload={};} open(){} setRequestHeader(){}
 send(){window.posts++; queueMicrotask(()=>{if(window.mode==='network'){this.onerror();return;}
 this.status=201;this.responseText=JSON.stringify({id:'film-1'});this.onload();});}
};
}"""
FILM = {'id':'film-1','title':'保存した動画','width':1920,'height':1080,'duration':1,'bytes':100,
        'sha256':'0'*64,'media':'film.mp4','url':'/film.mp4','ai_generated':False}

class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw=sync_playwright().start()
        path=os.environ.get('CHROMIUM_EXECUTABLE')
        cls.browser=cls.pw.chromium.launch(headless=True, **({'executable_path':path} if path else {}))
    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.pw.stop()
    def setUp(self):
        self.context=self.browser.new_context()
        # No navigation or network: exercise the real DOM function in an isolated document.
        self.context.route('**/*', lambda route: route.abort())
        self.page=self.context.new_page()
        self.page.set_content(HTML)
        self.page.evaluate(MOCK_TRANSPORT)
        source=SOURCE.read_text().replace('export async function', 'async function', 1)
        self.page.evaluate('async () => {' + source +
                           "; await mountFinalFilms(document.querySelector('#root'),'example');}")
    def tearDown(self):
        self.context.close()
    def fill(self):
        self.page.locator('input[name=file]').set_input_files({'name':'fixture.mp4','mimeType':'video/mp4','buffer':b'fictional test bytes'})
        self.page.locator('input[name=title]').fill('紹介動画 v1')
        self.page.locator('input[name=rights]').check()
    def test_saved_upload_and_failed_list_are_distinguished(self):
        self.page.evaluate('window.failGetAt=[2]');self.fill();self.page.locator('button[type=submit]').click()
        self.page.wait_for_function("document.querySelector('.final-message').textContent.includes('保存は完了')")
        self.assertEqual(self.page.locator('input[name=title]').input_value(),'')
        self.assertEqual(self.page.evaluate('window.posts'),1)
        self.page.evaluate('(film)=>{window.items=[film]}',FILM);self.page.locator('.final-reload').click()
        self.page.wait_for_selector('.final-review h3')
        self.assertEqual(self.page.locator('.final-review h3').inner_text(),'保存した動画')
        self.assertEqual(self.page.evaluate('window.posts'),1)
    def test_network_error_preserves_input_and_recheck_does_not_repost(self):
        self.page.evaluate("window.mode='network'");self.fill();self.page.locator('button[type=submit]').click()
        self.page.wait_for_function("document.querySelector('.final-message').textContent.includes('通信が切れ')")
        self.assertEqual(self.page.locator('input[name=title]').input_value(),'紹介動画 v1')
        self.page.locator('.final-reload').click()
        self.page.wait_for_function("document.querySelector('.final-message').textContent.includes('再送信していません')")
        self.assertEqual(self.page.evaluate('window.posts'),1)
    def test_failed_read_can_be_retried_without_losing_input(self):
        self.fill();self.page.evaluate('window.failGetAt=[2]');self.page.locator('.final-reload').click()
        self.page.wait_for_function("document.querySelector('.final-message').textContent.includes('読み込めません')")
        self.assertTrue(self.page.locator('.final-reload').is_enabled())
        self.assertEqual(self.page.locator('input[name=title]').input_value(),'紹介動画 v1')
        self.assertEqual(self.page.evaluate('window.posts'),0)

if __name__=='__main__':unittest.main()

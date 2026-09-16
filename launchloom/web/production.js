const $ = (q) => document.querySelector(q);
let plan, rev, cid = '', dirty = false, busy = false;
const message = (text, error = false) => { $('#message').textContent = text; $('#message').classList.toggle('error', error); };
function changed() { dirty = true; $('#save-state').textContent = '変更あり · まだ保存していません'; totals(); }
function totals() { $('#total').textContent = String(Math.round(plan.scenes.reduce((s, x) => s + Number(x.seconds || 0), 0) * 1000) / 1000); }
function blocked(value) { busy = value; $('#editor').inert = value; $('#campaign').disabled = value; $('#reload').disabled = value; }
async function api(path, options = {}) {
  const r = await fetch(path, {credentials: 'same-origin', ...options});
  if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(r.status === 401 ? '先に録画・書き出し画面で、起動時のアクセスキーを入力してください。' : e.detail || `HTTP ${r.status}`); }
  return r;
}
function draw() {
  $('#title').value = plan.title; $('#ratio').value = plan.aspect_ratio; $('#fps').value = String(plan.fps);
  $('#scenes').replaceChildren();
  plan.scenes.forEach((scene, index) => {
    const card = $('#scene-template').content.firstElementChild.cloneNode(true);
    card.querySelector('.scene-number').textContent = `SCENE ${String(index + 1).padStart(2, '0')}`;
    const asset = card.querySelector('.asset');
    const labelAsset = () => { asset.textContent = scene.source === 'after_effects' ? '基本タイムライン + 人による調整' : `assets/${scene.id}.mp4`; };
    labelAsset();
    card.querySelectorAll('[data-field]').forEach(input => {
      const key = input.dataset.field; input.value = scene[key];
      input.addEventListener('input', () => { scene[key] = key === 'seconds' ? Number(input.value) : input.value; changed(); labelAsset(); });
    });
    card.querySelector('[data-action="up"]').disabled = index === 0;
    card.querySelector('[data-action="down"]').disabled = index === plan.scenes.length - 1;
    card.querySelector('[data-action="remove"]').disabled = plan.scenes.length === 1;
    card.querySelectorAll('[data-action]').forEach(button => button.addEventListener('click', () => {
      const action = button.dataset.action;
      if (action === 'remove') plan.scenes.splice(index, 1);
      else { const next = index + (action === 'up' ? -1 : 1); [plan.scenes[index], plan.scenes[next]] = [plan.scenes[next], plan.scenes[index]]; }
      changed(); draw();
    }));
    $('#scenes').append(card);
  });
  $('#add').disabled = plan.scenes.length >= 12; totals();
}
async function load(id) {
  if (busy) return;
  blocked(true);
  try {
    const data = await (await api(`/api/campaigns/${encodeURIComponent(id)}/production`)).json();
    cid = id; plan = data.plan; rev = data.revision; dirty = false;
    $('#editor').hidden = false; draw();
    $('#save-state').textContent = data.saved ? '保存済み · 動画は未生成' : '初期構成 · 未保存';
    message('シーンを編集できます。外部サービスは呼び出しません。');
  } catch (e) { $('#campaign').value = cid; message(e.message, true); }
  finally { blocked(false); }
}
async function save() {
  if (!$('#editor').reportValidity()) throw new Error('入力内容を確認してください。');
  const data = await (await api(`/api/campaigns/${encodeURIComponent(cid)}/production`, {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({plan, expected_revision: rev})})).json();
  plan = data.plan; rev = data.revision; dirty = false; draw();
  $('#save-state').textContent = '保存済み · 動画は未生成';
}
$('#editor').addEventListener('submit', async e => {
  e.preventDefault(); if (busy) return; blocked(true);
  try { await save(); message('構成を保存しました。既存の映像と公開承認は変更していません。'); }
  catch (error) { message(error.message, true); }
  finally { blocked(false); }
});
$('#export').addEventListener('click', async () => {
  if (busy) return; blocked(true);
  try {
    await save();
    const r = await api(`/api/campaigns/${encodeURIComponent(cid)}/production/export`, {method: 'POST'});
    if (r.headers.get('X-Production-Revision') !== rev) throw new Error('別の画面で構成が変わりました。再読み込みしてください。');
    const blob = await r.blob(), url = URL.createObjectURL(blob), a = document.createElement('a');
    a.href = url; a.download = 'launchloom-production.zip'; document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    message('制作指示とJSXを書き出しました。動画・AEプロジェクトはまだ生成されていません。');
  } catch (e) { message(e.message, true); }
  finally { blocked(false); }
});
$('#add').addEventListener('click', () => {
  if (plan.scenes.length >= 12) return;
  plan.scenes.push({id: `scene-${crypto.randomUUID().slice(0, 8)}`, source: 'after_effects', seconds: 4, title: '新しいシーン', prompt: ''}); changed(); draw();
});
for (const [id, key] of [['title', 'title'], ['ratio', 'aspect_ratio'], ['fps', 'fps']]) $('#'+id).addEventListener('input', e => { plan[key] = key === 'fps' ? Number(e.target.value) : e.target.value; changed(); });
$('#campaign').addEventListener('change', e => {
  if (dirty && !confirm('未保存の変更を破棄して切り替えますか？')) { e.target.value = cid; return; }
  load(e.target.value);
});
$('#reload').addEventListener('click', () => { if (!dirty || confirm('未保存の変更を破棄して読み直しますか？')) { if (cid) load(cid); else init(); } });
window.addEventListener('beforeunload', e => { if (dirty) { e.preventDefault(); e.returnValue = ''; } });
async function init() {
  try {
    const campaigns = await (await api('/api/campaigns')).json();
    $('#campaign').replaceChildren();
    for (const c of campaigns) { const option = document.createElement('option'); option.value = c.id; option.textContent = c.brief?.name || c.name || c.id; $('#campaign').append(option); }
    if (!campaigns.length) { message('録画・書き出し画面でキャンペーンを作成してから、ここへ戻ってください。'); return; }
    await load(campaigns[0].id);
  } catch (e) { message(e.message, true); }
}
init();

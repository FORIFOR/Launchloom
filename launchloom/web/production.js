import {mountFinalFilms} from './final-films.js';
const $ = (q) => document.querySelector(q);
let plan, rev, cid = '', dirty = false, busy = false, execution = null;
const message = (text, error = false) => { $('#message').textContent = text; $('#message').classList.toggle('error', error); };
function changed() { dirty = true; $('#save-state').textContent = '変更あり · まだ保存していません'; totals(); if (execution) drawExecution(execution); }
function totals() { $('#total').textContent = String(Math.round(plan.scenes.reduce((s, x) => s + Number(x.seconds || 0), 0) * 1000) / 1000); }
function blocked(value) { busy = value; $('#editor').inert = value; $('#campaign').disabled = value; $('#reload').disabled = value; const root=$('#execution-root'); if(root) root.inert=value; }
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
    const role = card.querySelector('.scene-role');
    const asset = card.querySelector('.asset');
    const labels = {recording: ['PRODUCT / 実際の動作', `assets/${scene.id}.mp4`], seedance: ['ATMOSPHERE / 雰囲気', `assets/${scene.id}.mp4`], after_effects: ['MOTION / 文字と演出', '基本タイムライン + 人による調整']};
    const labelAsset = () => { const label=labels[scene.source] || ['SCENE', `assets/${scene.id}.mp4`]; role.textContent=label[0]; asset.textContent=label[1]; card.dataset.source=scene.source; };
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
    $('#campaign').value=cid;
    $('#back-studio').href='/?campaign='+encodeURIComponent(cid);
    $('#back-distribution').href='/?campaign='+encodeURIComponent(cid)+'&tab=distribution';
    history.replaceState(null,'','/production?campaign='+encodeURIComponent(cid));
    await mountFinalFilms($('#final-films-root'), cid);
    await loadExecution();
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
  await loadExecution();
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

function node(tag, text = '', cls = '') {
  const value = document.createElement(tag); if (text) value.textContent = text; if (cls) value.className = cls; return value;
}
function capabilityText(enabled, available='設定済み', missing='未設定') { return enabled ? available : missing; }
async function loadExecution() {
  if (!cid) return;
  try {
    execution = await (await api(`/api/campaigns/${encodeURIComponent(cid)}/production/execution`)).json();
    drawExecution(execution);
  } catch (e) {
    execution = null; const root=$('#execution-root'); root.replaceChildren(node('p', e.message, 'execution-message error'));
  }
}
async function executeJson(path, body, confirmation) {
  if (busy || dirty) { message(dirty ? '先に構成を保存してください。' : '別の処理が実行中です。', true); return; }
  if (confirmation && !confirm(confirmation)) return;
  blocked(true);
  try {
    const result = await (await api(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)})).json();
    message('制作処理が完了しました。公開・SNS投稿は行っていません。');
    await loadExecution(); await mountFinalFilms($('#final-films-root'), cid);
    return result;
  } catch (e) { message(e.message, true); }
  finally { blocked(false); }
}
async function uploadScene(scene, file, aiGenerated) {
  if (!file) return;
  if (dirty) { message('素材を入れる前に構成を保存してください。', true); return; }
  if (file.size > 200*1024*1024) { message('シーン素材は200 MB以下にしてください。', true); return; }
  if (!confirm(`${scene.id} の動画・音声を利用する権利を確認しましたか？`)) return;
  blocked(true);
  try {
    const query=new URLSearchParams({expected_revision:rev,rights_confirmed:'true',ai_generated:String(!!aiGenerated)});
    await api(`/api/campaigns/${encodeURIComponent(cid)}/production/scenes/${encodeURIComponent(scene.id)}/media?${query}`, {method:'POST',body:file,headers:{'Content-Type':'application/octet-stream'}});
    message(`${scene.id} の素材を準備しました。`); await loadExecution();
  } catch(e) { message(e.message,true); }
  finally { blocked(false); }
}
function drawExecution(data) {
  const root=$('#execution-root'); root.replaceChildren();
  if (!data.saved) { root.append(node('p','構成を保存すると、版に固定した制作実行が使えます。','execution-message')); return; }
  const panel=node('div','','execution-panel');
  const canRun=!dirty && !data.busy;
  for (const scene of data.scenes) {
    if (scene.source === 'after_effects') continue;
    const row=node('div','','execution-row');
    const copy=node('div'); copy.append(node('h3',`${scene.id} · ${scene.source==='seedance'?'Seedance':'Recording'}`));
    copy.append(node('p', scene.asset ? `素材あり · ${scene.asset.width}×${scene.asset.height} · ${scene.asset.duration}秒` : '素材はまだありません。'));
    const status=node('span',scene.asset ? 'READY' : 'NEEDS MEDIA',`execution-status ${scene.asset?'ready':'blocked'}`); copy.append(status); row.append(copy);
    const note=node('div');
    if(scene.source==='seedance') note.append(node('p',scene.seedance_blocked || `720p概算 $${Number(scene.estimate_720p_usd||0).toFixed(3)} · 実課金はprovider側で確定`));
    else note.append(node('p','H.264/AAC MP4を取り込みます。メタデータ除去と全体デコードを行います。'));
    row.append(note);
    const controls=node('div','','execution-controls');
    const file=document.createElement('input'); file.type='file'; file.accept='video/mp4,video/quicktime'; file.setAttribute('aria-label',`${scene.id}の素材動画`); controls.append(file);
    const aiLabel=node('label','','scene-ai-label'); const ai=document.createElement('input'); ai.type='checkbox'; ai.setAttribute('aria-label',`${scene.id}はAI生成素材`); aiLabel.append(ai,document.createTextNode(' AI生成素材')); controls.append(aiLabel);
    const upload=node('button','素材を入れる'); upload.type='button'; upload.disabled=!canRun; upload.addEventListener('click',()=>uploadScene(scene,file.files[0],ai.checked)); controls.append(upload);
    if(scene.source==='seedance') {
      const resolution=document.createElement('select'); for(const x of ['720p','480p']) {const o=document.createElement('option');o.value=x;o.textContent=x;resolution.append(o)} controls.append(resolution);
      const generate=node('button','Seedanceで生成','paid'); generate.type='button'; generate.disabled=!canRun || !data.capabilities.seedance || !!scene.seedance_blocked;
      generate.title=data.capabilities.seedance?'有料生成を明示実行します':'FAL_KEY / ENABLE_PAID_GENERATION が必要です';
      generate.addEventListener('click',()=>executeJson(`/api/campaigns/${encodeURIComponent(cid)}/production/scenes/${encodeURIComponent(scene.id)}/seedance`,{expected_revision:rev,resolution:resolution.value,generate_audio:true,confirmed:true},`Seedance 2.5で ${scene.id} を生成します。720p概算は約 $${Number(scene.estimate_720p_usd||0).toFixed(3)} です。providerの実課金が発生することを確認して実行しますか？`)); controls.append(generate);
    }
    row.append(controls); panel.append(row);
  }
  const agentRow=node('div','','execution-row'); const agentCopy=node('div'); agentCopy.append(node('h3','Motion script · Codex / Claude Code')); agentCopy.append(node('p','隔離workspaceで build.jsx だけを改善します。ネットワーク・Bashは許可しません。')); agentRow.append(agentCopy);
  const agentState=node('div'); agentState.append(node('span',data.agent?`${data.agent.name}で更新済み`:'未実行',`execution-status ${data.agent?'ready':'blocked'}`)); agentRow.append(agentState);
  const agentControls=node('div','','execution-controls'); const agentSelect=document.createElement('select');
  for(const [value,label] of [['codex','Codex'],['claude','Claude Code']]) {const o=document.createElement('option');o.value=value;o.textContent=`${label} · ${capabilityText(data.capabilities[value])}`;o.disabled=!data.capabilities[value];agentSelect.append(o)}
  agentControls.append(agentSelect); const agentButton=node('button','JSXを改善','run'); agentButton.type='button'; agentButton.disabled=!canRun || (!data.capabilities.codex&&!data.capabilities.claude);
  agentButton.addEventListener('click',()=>executeJson(`/api/campaigns/${encodeURIComponent(cid)}/production/agent`,{expected_revision:rev,agent:agentSelect.value,confirmed:true},`${agentSelect.value==='codex'?'Codex':'Claude Code'}を隔離workspaceで実行し、build.jsxの変更だけを採用しますか？`)); agentControls.append(agentButton); agentRow.append(agentControls); panel.append(agentRow);
  const aeRow=node('div','','execution-row'); const aeCopy=node('div'); aeCopy.append(node('h3','After Effects')); aeCopy.append(node('p','Windowsはreviewed JSXからAEP作成を自動化。macOSはJSXをAEで手動実行し、aerenderから自動化できます。')); aeRow.append(aeCopy);
  const aeState=node('div'); const project=!!data.after_effects?.project, rendered=!!data.after_effects?.render; aeState.append(node('span',rendered?'FINAL REGISTERED':project?'AEP READY':'NOT RUN',`execution-status ${project||rendered?'ready':'blocked'}`)); aeRow.append(aeState);
  const aeControls=node('div','','execution-controls'); const projectButton=node('button','AEPを作成');projectButton.type='button';projectButton.disabled=!canRun||!data.capabilities.after_effects_project;projectButton.addEventListener('click',()=>executeJson(`/api/campaigns/${encodeURIComponent(cid)}/production/after-effects/project`,{expected_revision:rev,confirmed:true},'reviewed build.jsxをAfter Effectsで実行してAEPを作成しますか？既存AEPは上書きしません。'));aeControls.append(projectButton);
  const renderButton=node('button','aerender → 完成版','run');renderButton.type='button';renderButton.disabled=!canRun||!data.capabilities.aerender;renderButton.addEventListener('click',()=>executeJson(`/api/campaigns/${encodeURIComponent(cid)}/production/after-effects/render`,{expected_revision:rev,confirmed:true},'review済みAEPをaerenderし、新しい完成動画の版として登録しますか？公開許可は保留に戻ります。'));aeControls.append(renderButton);aeRow.append(aeControls);panel.append(aeRow);
  root.append(panel);
  const warning=node('p','設定されていない工程は無効です。ここからSNSへは投稿しません。実課金・実Adobe実行は各ボタンの確認後だけ行われます。','execution-warning');root.append(warning);
}

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
    const wanted=new URLSearchParams(location.search).get('campaign');
    await load((campaigns.find(c=>c.id===wanted)||campaigns[0]).id);
  } catch (e) { message(e.message, true); }
}
init();

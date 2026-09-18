const $ = (id) => document.getElementById(id);
const ja = (localStorage.getItem('launchloom-creative-language') || navigator.language || 'en').startsWith('ja');
const t = (j, e) => ja ? j : e;
document.documentElement.lang = ja ? 'ja' : 'en';
if (!ja) document.querySelectorAll('[data-en]').forEach((node) => { node.textContent = node.dataset.en; });
$('language').textContent = ja ? 'EN' : '日本語';
$('language').onclick = () => {
  if (dirty && !confirm(t('未保存の編集を破棄して言語を切り替えますか？', 'Discard unsaved edits and change language?'))) return;
  localStorage.setItem('launchloom-creative-language', ja ? 'en' : 'ja'); location.reload();
};
$('instruction').placeholder = t('文字を上へ / 2秒短く / 5秒にする', 'text higher / shorten by 2 / set to 5');
let cid = '', data = null, spec = null, index = 0, output = 'landscape';
let dirty = false, pending = false, generation = 0, pollTimer = null, selectedJob = null, view = 'layout';
const notice = (text, error = false) => { $('message').textContent = text; $('message').classList.toggle('error', error); };
const base = (id = cid) => `/api/campaigns/${encodeURIComponent(id)}`;
function errorText(value) {
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return value.map((x) => `${x.scene_id || x.loc?.join('.') || ''}: ${x.message || x.msg || ''}`).join('\n');
  return t('処理できませんでした。入力を確認してください。', 'Could not complete this action. Check the input.');
}
async function api(path, method = 'GET', body) {
  const response = await fetch(path, {method, credentials: 'same-origin',
    headers: body === undefined ? {} : {'Content-Type': 'application/json'},
    body: body === undefined ? undefined : JSON.stringify(body)});
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) $('access-form').hidden = false;
    throw new Error(response.status === 401 ? t('起動時のアクセスキーで接続してください。', 'Connect with the local access key printed at startup.') : errorText(result.detail));
  }
  return result;
}
function element(tag, text, cls) {
  const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (cls) node.className = cls; return node;
}
function option(value, label) { const o = element('option', label); o.value = value; return o; }
function scene() { return spec.scenes[index]; }
function layout() { return scene().layouts[output] || {y: 0.78, size: 0.055}; }
function edited() { dirty = true; $('reviewed').checked = false; view = 'layout'; refreshPreview(); controls(); }
function controls() {
  if (!spec) return;
  const stale = data.source_changed;
  $('save-state').textContent = pending ? t('処理中', 'Working') : dirty ? t('変更あり · 未保存', 'Unsaved changes') : data.derived ? t('初期構成 · 保存してください', 'Initial composition · save first') : t('保存済み', 'Saved');
  $('editor-fields').disabled = pending || stale;
  $('save').disabled = pending || stale || (!dirty && !data.derived);
  $('suggest').disabled = pending || stale || dirty || data.derived;
  $('render-scene').disabled = $('render-all').disabled = pending || stale || dirty || data.derived || !$('rights').checked;
  $('try-sample').disabled = pending;
  $('reset').disabled = pending;
  $('video-mode').disabled = !selectedJob?.result?.outputs?.[output];
  const adoptable = selectedJob?.state === 'ready' && selectedJob.scene_id === null && selectedJob.revision === data.revision && !dirty && !stale && view === 'video' && !!selectedJob.result.outputs[output];
  $('adoption').hidden = !adoptable;
  $('adopt').disabled = !adoptable || pending || !$('rights').checked || !$('reviewed').checked;
  $('move-left').disabled = index === 0;
  $('move-right').disabled = index === spec.scenes.length - 1;
  $('progress').hidden = !pending;
}
function refreshPreview() {
  if (!spec) return;
  const current = scene();
  $('stage').dataset.output = output; $('stage').dataset.preset = spec.brand.preset;
  $('stage').style.setProperty('--accent', spec.brand.accent);
  $('landscape').setAttribute('aria-pressed', String(output === 'landscape'));
  $('portrait').setAttribute('aria-pressed', String(output === 'portrait'));
  $('landscape').disabled = !spec.outputs.includes('landscape');
  $('portrait').disabled = !spec.outputs.includes('portrait');
  const showFilm = view === 'video' && !!selectedJob?.result?.outputs?.[output];
  $('layout-preview').hidden = showFilm; $('film').hidden = !showFilm;
  $('layout-mode').setAttribute('aria-pressed', String(!showFilm)); $('video-mode').setAttribute('aria-pressed', String(showFilm));
  if (showFilm) {
    const src = selectedJob.result.outputs[output].url;
    if ($('film').getAttribute('src') !== src) { $('film').pause(); $('film').src = src; }
    const suffix = selectedJob.revision !== data.revision || dirty ? t(' · 以前の構成', ' · earlier composition') : '';
    $('preview-kind').textContent = (selectedJob.scene_id ? t('シーン単体のプレビュー · 未採用', 'Single-scene preview · not adopted') : t('レンダー済みの全体映像 · 公開前', 'Rendered film · not published')) + suffix;
  } else {
    $('film').pause();
    $('preview-kind').textContent = t('概略の構図です。動きと正確な文字組みはレンダー後に確認できます。', 'Approximate composition. Render to inspect motion and exact typography.');
  }
  $('brand-preview').textContent = spec.brand.name;
  $('copy-preview').textContent = current.layers.filter((l) => l.kind === 'text').map((l) => l.text).join('\n');
  $('copy-preview').style.top = `${layout().y * 100}%`;
  $('copy-preview').style.fontSize = `${layout().size * (output === 'landscape' ? 56.25 : 100)}cqw`;
  $('footage-placeholder').hidden = !current.layers.some((l) => ['recording', 'generated_video'].includes(l.kind));
  const frames = spec.scenes.reduce((n, s) => n + Math.round(s.seconds * spec.fps), 0);
  $('duration').textContent = `${(frames / spec.fps).toFixed(1)}s · ${spec.fps}fps`;
  $('scene-count').textContent = `${index + 1} / ${spec.scenes.length}`;
}
function drawTimeline() {
  $('timeline').replaceChildren();
  spec.scenes.forEach((s, i) => {
    const button = element('button'); button.type = 'button'; button.setAttribute('aria-pressed', String(i === index));
    button.append(element('span', `SCENE ${String(i + 1).padStart(2, '0')} · ${s.seconds.toFixed(1)}s`), element('strong', s.title || s.id));
    button.onclick = () => { index = i; view = 'layout'; draw(); };
    $('timeline').append(button);
  });
}
function draw() {
  const s = scene();
  $('scene-label').textContent = `SCENE ${String(index + 1).padStart(2, '0')}`;
  $('scene-heading').textContent = s.title || s.id;
  $('scene-title').value = s.title; $('seconds').value = s.seconds; $('camera').value = s.camera;
  $('caption-y').value = layout().y; $('caption-size').value = layout().size;
  $('caption-y-value').textContent = `${Math.round(layout().y * 100)}%`;
  $('copy-fields').replaceChildren();
  s.layers.filter((l) => l.kind === 'text').forEach((layer) => {
    const label = element('label'); label.append(element('span', t('画面に出す言葉', 'On-screen copy')));
    const input = element('textarea'); input.rows = 3; input.maxLength = 500; input.value = layer.text; input.required = true;
    input.oninput = () => { layer.text = input.value; edited(); }; label.append(input); $('copy-fields').append(label);
  });
  $('asset-fields').replaceChildren();
  s.layers.filter((l) => ['recording', 'generated_video'].includes(l.kind)).forEach((layer) => {
    const label = element('label'); label.append(element('span', t('使用する映像', 'Prepared media')));
    const select = element('select'); select.append(option('', t('素材を選択', 'Choose prepared media')));
    data.assets.filter((a) => s.purpose !== 'proof' || a.kind === 'recording').forEach((a) => select.append(option(a.id, `${a.id} · ${a.duration.toFixed(1)}s · ${a.kind === 'recording' ? t('実録画', 'recorded') : t('生成映像', 'generated')}`)));
    select.value = layer.asset_id;
    select.onchange = () => {
      const a = data.assets.find((item) => item.id === select.value); if (!a) return;
      layer.asset_id = a.id; layer.asset_sha256 = a.sha256; layer.kind = a.kind;
      layer.role = s.purpose === 'proof' ? 'evidence' : 'concept'; layer.generator = ''; edited();
    };
    label.append(select); $('asset-fields').append(label);
    const startLabel = element('label'); startLabel.append(element('span', t('素材内の開始位置 / 秒', 'Source start / seconds')));
    const start = element('input'); start.type = 'number'; start.min = '0'; start.max = '300'; start.step = '0.1'; start.value = layer.start_seconds;
    start.oninput = () => { layer.start_seconds = Number(start.value); edited(); }; startLabel.append(start); $('asset-fields').append(startLabel);
  });
  if (s.purpose !== 'proof' && s.layers.some((l) => ['recording', 'generated_video'].includes(l.kind))) {
    const remove = element('button', t('このシーンを文字だけにする', 'Make this scene type-only')); remove.type = 'button';
    remove.onclick = () => { s.layers = s.layers.filter((l) => !['recording', 'generated_video'].includes(l.kind)); edited(); draw(); };
    $('asset-fields').append(remove);
  }
  $('claim-field').hidden = s.purpose !== 'proof';
  $('claim').replaceChildren(option('', t('承認済みの機能を選択', 'Choose an approved feature')));
  data.claims.forEach((c) => $('claim').append(option(c.id, c.title))); $('claim').value = s.claim_ids[0] || '';
  $('brand-name').value = spec.brand.name; $('preset').value = spec.brand.preset;
  $('accent').value = spec.brand.accent; $('direction').value = spec.brand.visual_direction;
  $('blockers').replaceChildren();
  (data.preflight || []).filter((b) => b.scene_id === s.id).forEach((b) => $('blockers').append(element('p', b.message)));
  drawTimeline(); refreshPreview(); controls();
}
function bind(id, update) { $(id).addEventListener('input', () => { if (!spec) return; update($(id).value); edited(); }); }
bind('scene-title', (v) => { scene().title = v; $('scene-heading').textContent = v; drawTimeline(); });
bind('seconds', (v) => { scene().seconds = Number(v); drawTimeline(); });
bind('camera', (v) => { scene().camera = v; });
bind('caption-y', (v) => { scene().layouts[output] = {...layout(), y: Number(v)}; $('caption-y-value').textContent = `${Math.round(Number(v) * 100)}%`; });
bind('caption-size', (v) => { scene().layouts[output] = {...layout(), size: Number(v)}; });
bind('claim', (v) => { scene().claim_ids = v ? [v] : []; });
bind('brand-name', (v) => { spec.brand.name = v; }); bind('preset', (v) => { spec.brand.preset = v; });
bind('accent', (v) => { spec.brand.accent = v; }); bind('direction', (v) => { spec.brand.visual_direction = v; });
for (const id of ['rights', 'reviewed']) $(id).onchange = controls;
for (const format of ['landscape', 'portrait']) $(format).onclick = () => { output = format; $('reviewed').checked = false; draw(); };
$('layout-mode').onclick = () => { view = 'layout'; refreshPreview(); controls(); };
$('video-mode').onclick = () => { view = 'video'; refreshPreview(); controls(); };
for (const [id, delta] of [['move-left', -1], ['move-right', 1]]) $(id).onclick = () => {
  const next = index + delta; if (next < 0 || next >= spec.scenes.length) return;
  [spec.scenes[index], spec.scenes[next]] = [spec.scenes[next], spec.scenes[index]]; index = next; edited(); draw();
};
function selectRender(job) {
  selectedJob = job; $('reviewed').checked = false;
  if (job.result && !job.result.outputs[output]) output = Object.keys(job.result.outputs)[0];
  if (job.result) {
    const reused = job.result.scenes.filter((s) => s.reused).length;
    $('render-summary').textContent = t(`再利用 ${reused} / 再制作 ${job.result.scenes.length - reused}`, `Reused ${reused} / rebuilt ${job.result.scenes.length - reused}`);
    view = 'video';
  }
  draw();
}
async function historyList(token = generation) {
  const value = await api(`${base()}/creative-renders`); if (token !== generation) return;
  $('history').replaceChildren();
  value.items.forEach((job) => {
    const button = element('button'); button.type = 'button';
    button.append(element('span', `${new Date(job.created * 1000).toLocaleString()} · ${job.scene_id || t('全体', 'Full film')}`), element('span', job.state));
    button.disabled = job.state !== 'ready'; button.onclick = () => selectRender(job); $('history').append(button);
  });
  const active = value.items.find((job) => ['queued', 'running'].includes(job.state));
  if (active) { pending = true; poll(active.id, token); }
  else if (!selectedJob) { const latest = value.items.find((j) => j.state === 'ready'); if (latest) selectRender(latest); }
  controls();
}
async function load(id, force = false) {
  if (dirty && !force && !confirm(t('未保存の編集を破棄しますか？', 'Discard unsaved edits?'))) { $('campaign').value = cid; return; }
  const token = ++generation; clearTimeout(pollTimer);
  pending = false; selectedJob = null; $('film').pause(); $('workspace').hidden = true;
  try {
    const next = await api(`${base(id)}/creative-spec`); if (token !== generation) return;
    cid = id; data = next; spec = structuredClone(next.spec); index = 0; dirty = false;
    output = spec.outputs.includes(output) ? output : spec.outputs[0]; view = 'layout';
    $('campaign').value = cid; $('rights').checked = $('reviewed').checked = false;
    $('render-summary').textContent = '';
    history.replaceState(null, '', `/creative?campaign=${encodeURIComponent(cid)}`);
    $('legacy-link').href = `/production?campaign=${encodeURIComponent(cid)}`;
    $('distribution-link').href = `/?campaign=${encodeURIComponent(cid)}&tab=distribution`;
    $('source-warning').hidden = !data.source_changed;
    $('workspace').hidden = false; draw();
    notice(t('映像やコピーを編集できます。保存だけでは生成・公開しません。', 'Edit your footage and copy. Saving does not generate or publish anything.'));
    await historyList(token);
  } catch (error) { if (token === generation) notice(error.message, true); }
}
async function refreshCampaigns(preferred) {
  const items = await api('/api/campaigns'); $('access-form').hidden = true; $('campaign').replaceChildren();
  items.forEach((item) => $('campaign').append(option(item.id, item.brief.name)));
  const requested = preferred || new URLSearchParams(location.search).get('campaign');
  const id = items.some((item) => item.id === requested) ? requested : items[0]?.id;
  if (id) await load(id, true); else notice(t('キャンペーンがありません。「実アプリのサンプルで試す」から始められます。', 'No campaigns yet. Start with the real app sample.'));
}
$('campaign').onchange = () => load($('campaign').value);
$('reload').onclick = () => cid ? load(cid) : refreshCampaigns().catch((e) => notice(e.message, true));
$('access-form').onsubmit = async (event) => {
  event.preventDefault();
  try { await api('/api/session', 'POST', {token: $('access-key').value}); $('access-key').value = ''; await refreshCampaigns(); }
  catch (error) { notice(error.message, true); }
};
$('save').onclick = async () => {
  const token = generation;
  try {
    pending = true; controls();
    const saved = await api(`${base()}/creative-spec`, 'PUT', {spec, expected_revision: data.revision, production_revision: data.production_revision});
    if (token !== generation) return;
    data = {...data, ...saved, source_changed: false}; spec = structuredClone(saved.spec); dirty = false;
    const latest = await api(`${base()}/creative-spec`); if (token !== generation) return;
    data = latest; draw(); notice(t('保存しました。採用済みの動画と投稿は変更していません。', 'Saved. Adopted films and posts are unchanged.'));
  } catch (error) { if (token === generation) notice(error.message, true); }
  finally { if (token === generation) { pending = false; controls(); } }
};
$('quick-edit').onsubmit = async (event) => {
  event.preventDefault(); if (dirty || data.derived || pending) return;
  const token = generation;
  try {
    const candidate = await api(`${base()}/creative-spec/propose-edit`, 'POST', {expected_revision: data.revision, production_revision: data.production_revision, scene_id: scene().id, instruction: $('instruction').value, output});
    if (token !== generation) return;
    spec = candidate.spec; edited(); draw(); notice(t('下書きに反映しました。内容を確認して保存してください。', 'Applied to the draft. Review and save the change.'));
  } catch (error) { if (token === generation) notice(error.message, true); }
};
async function poll(jid, token) {
  clearTimeout(pollTimer);
  try {
    const result = await api(`${base()}/creative-renders/${jid}`); if (token !== generation) return;
    $('progress').max = result.total || 1; $('progress').value = result.completed;
    if (['queued', 'running'].includes(result.state)) {
      pending = true; controls(); notice(t(`シーンを制作中 ${result.completed} / ${result.total || '…'}`, `Rendering scenes ${result.completed} / ${result.total || '…'}`));
      pollTimer = setTimeout(() => poll(jid, token), 900); return;
    }
    pending = false;
    if (result.state === 'ready') {
      selectRender(result); notice(t('レンダーが完了しました。再生して確認できます。まだ完成版への採用・公開はしていません。', 'Render complete. Play it to review. It has not been adopted or published.'));
    } else notice(result.error || result.state, true);
    controls(); await historyList(token);
  } catch (error) {
    if (token !== generation) return;
    pending = false; controls(); notice(t(`状態の取得に失敗しました。再送せず「再読み込み」で確認してください。 ${error.message}`, `Could not read render status. Reload to reconcile; do not resubmit. ${error.message}`), true);
  }
}
async function render(single) {
  if (pending || dirty || data.derived || !$('rights').checked) return;
  const token = generation;
  try {
    pending = true; controls(); $('reviewed').checked = false;
    notice(t('保存した構成をレンダリングしています。', 'Rendering the saved composition.'));
    const result = await api(`${base()}/creative-renders`, 'POST', {expected_revision: data.revision, production_revision: data.production_revision, scene_id: single ? scene().id : null, outputs: single ? [output] : spec.outputs, rights_confirmed: true});
    if (token === generation) await poll(result.id, token);
  } catch (error) { if (token === generation) { pending = false; controls(); notice(error.message, true); } }
}
$('render-scene').onclick = () => render(true); $('render-all').onclick = () => render(false);
$('adopt').onclick = async () => {
  if (!$('reviewed').checked || !$('rights').checked || pending || dirty) return;
  const token = generation;
  try {
    pending = true; controls();
    const film = await api(`${base()}/creative-renders/${selectedJob.id}/adopt`, 'POST', {output, expected_revision: selectedJob.revision, rights_confirmed: true, content_reviewed: true});
    if (token !== generation) return;
    $('distribution-link').href = `/?campaign=${encodeURIComponent(cid)}&tab=distribution&media=${encodeURIComponent(film.media)}`;
    notice(t('新しい完成動画として採用しました。公開許可は保留です。「完成版・公開」から確認・承認に進めます。', 'Adopted as a new finished film. Publishing is held. Continue to Finished films & publishing for separate approval.'));
  } catch (error) { if (token === generation) notice(error.message, true); }
  finally { if (token === generation) { pending = false; controls(); } }
};
$('reset').onclick = async () => {
  if (!confirm(t('こちらの編集を、現在の元の構成で置き換えます。よろしいですか？採用済みの動画は残ります。', 'Replace these edits with the current original composition? Adopted films will remain.'))) return;
  try { await api(`${base()}/creative-spec/reset`, 'POST', {expected_revision: data.revision, production_revision: data.current_production_revision, confirmed: true}); dirty = false; await load(cid, true); }
  catch (error) { notice(error.message, true); }
};
$('try-sample').onclick = async () => {
  if (pending) return;
  if (dirty && !confirm(t('未保存の編集を破棄してサンプルを作りますか？', 'Discard unsaved edits and create the sample?'))) return;
  const token = ++generation; clearTimeout(pollTimer); dirty = false; pending = true; $('try-sample').disabled = true; if (spec) controls();
  try {
    const sample = await api(`/api/demo?language=${ja ? 'ja' : 'en'}`, 'POST');
    for (;;) {
      if (token !== generation) return;
      const record = await api(base(sample.id));
      notice(t('実アプリをローカルで録画しています。', 'Recording the real bundled app locally.') + ` ${record.stage || ''}`);
      if (record.state === 'ready') { pending = false; await refreshCampaigns(sample.id); return; }
      if (['failed', 'interrupted'].includes(record.state)) throw new Error(record.error || record.state);
      await new Promise((resolve) => setTimeout(resolve, 1200));
    }
  } catch (error) { if (token === generation) { pending = false; $('try-sample').disabled = false; if (spec) controls(); notice(error.message, true); } }
};
window.addEventListener('beforeunload', (event) => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
refreshCampaigns().catch((error) => notice(error.message, true));

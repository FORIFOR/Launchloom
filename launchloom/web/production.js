const $ = (q) => document.querySelector(q);
let plan, rev, cid = '', dirty = false, busy = false, finalEpoch=0, reviewing=null, uploading=false, generating=null, jobTimer=null, jobsConfigured=false, fetchingJobs=false;
const message = (text, error = false) => { $('#message').textContent = text; $('#message').classList.toggle('error', error); };
function changed() { dirty = true; $('#save-state').textContent = '変更あり · まだ保存していません'; totals(); }
function totals() { $('#total').textContent = String(Math.round(plan.scenes.reduce((s, x) => s + Number(x.seconds || 0), 0) * 1000) / 1000); }
function blocked(value) { busy = value; $('#editor').inert = value; $('#campaign').disabled = value || uploading; $('#reload').disabled = value || uploading; }
async function api(path, options = {}) {
  const r = await fetch(path, {credentials: 'same-origin', ...options});
  if(r.status===401 && !$('#login-dialog').open)$('#login-dialog').showModal();
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
    const generate = card.querySelector('.generate-scene');
    generate.addEventListener('click',()=>openGeneration(scene.id));
    const labelAsset = () => { generate.hidden=scene.source!=='seedance'; asset.textContent = scene.source === 'after_effects' ? '基本タイムライン + 人による調整' : `assets/${scene.id}.mp4`; };
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
  if (busy || uploading) return;
  blocked(true);
  try {
    const data = await (await api(`/api/campaigns/${encodeURIComponent(id)}/production`)).json();
    cid = id; history.replaceState(null,'','/production?campaign='+encodeURIComponent(cid));
    $('#studio-back').href='/?campaign='+encodeURIComponent(cid);
    plan = data.plan; rev = data.revision; dirty = false;
    $('#editor').hidden = false; draw();
    $('#save-state').textContent = data.saved ? '保存済み · 動画は未生成' : '初期構成 · 未保存';
    message('シーンを編集するか、完成した動画を取り込めます。');
    $('#final-section').hidden=false;
    await loadFinals();
    $('#generation-section').hidden=false;await loadJobs();
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
window.addEventListener('beforeunload', e => { if (dirty || uploading) { e.preventDefault(); e.returnValue = ''; } });
async function init() {
  try {
    const campaigns = await (await api('/api/campaigns')).json();
    $('#campaign').replaceChildren();
    for (const c of campaigns) { const option = document.createElement('option'); option.value = c.id; option.textContent = c.brief?.name || c.name || c.id; $('#campaign').append(option); }
    $('#empty-help').hidden=campaigns.length>0;
    if (!campaigns.length) { $('#empty-help').hidden=false; message('録画・書き出し画面でキャンペーンを作成してから、ここへ戻ってください。'); return; }
    const requested=new URLSearchParams(location.search).get('campaign');
    if(requested && !campaigns.some(c=>c.id===requested))throw new Error('指定されたキャンペーンがありません。制作スタジオから選び直してください。');
    const id=requested||campaigns[0].id;$('#campaign').value=id;await load(id);
  } catch (e) { message(e.message, true); }
}

async function loadFinals(){
  const data=await(await api(`/api/campaigns/${encodeURIComponent(cid)}/finals`)).json();
  finalEpoch=data.epoch;$('#final-list').replaceChildren();
  $('#to-distribution').hidden=!data.items.some(a=>a.selected);
  $('#to-distribution').href='/?campaign='+encodeURIComponent(cid)+'&tab=distribution';
  for(const item of data.items){
    const card=document.createElement('article');card.className='final-card';
    const video=document.createElement('video');video.controls=true;video.playsInline=true;video.preload='none';video.src=item.url;video.poster=item.poster;
    const title=document.createElement('h3');title.textContent=item.title;
    const meta=document.createElement('p');meta.textContent=`${item.width}×${item.height} · ${item.seconds.toFixed(1)}秒 · ${(item.bytes/1048576).toFixed(1)} MB · ${item.ai_generated?'生成AIを含む':'生成AIなし（申告）'}`;
    const button=document.createElement('button');button.type='button';button.textContent=item.selected?'採用中 · 配信画面で確認':'動画を確認して採用';
    if(item.selected)button.className='selected';
    button.addEventListener('click',()=>{
      if(item.selected){location.assign($('#to-distribution').href);return;}
      reviewing=item;$('#review-video').src=item.url;$('#review-meta').textContent=item.title+' / SHA-256 '+item.sha256;
      $('#film-review-form').reset();$('#review-status').textContent='';$('#film-review').showModal();
    });
    card.append(video,title,meta,button);$('#final-list').append(card);
  }
}
$('#review-close').onclick=()=>{$('#review-video').pause();$('#film-review').close();};
$('#film-review').addEventListener('close',()=>$('#review-video').pause());
$('#film-review-form').addEventListener('submit',async e=>{
  e.preventDefault();const button=$('#adopt-film');button.disabled=true;
  try{
    await api(`/api/campaigns/${encodeURIComponent(cid)}/finals/${reviewing.id}/select`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sha256:reviewing.sha256,expected_epoch:finalEpoch,content_reviewed:$('#final-content-reviewed').checked,rights_confirmed:$('#final-rights-reviewed').checked})});
    $('#film-review').close();await loadFinals();message('この版を採用しました。配信画面で公開許可・投稿内容を確認してください。');
  }catch(error){$('#review-status').textContent=error.message;}finally{button.disabled=false;}
});
$('#final-form').addEventListener('submit',async e=>{
  e.preventDefault();if(uploading)return;const file=$('#final-file').files[0];if(!file)return;
  if(file.size>200*1024*1024){$('#upload-state').textContent='200 MB以下のファイルを選んでください。';return;}
  uploading=true;$('#final-upload').disabled=true;$('#campaign').disabled=true;$('#reload').disabled=true;
  const params=new URLSearchParams({title:$('#final-title').value,rights_confirmed:String($('#final-rights').checked),ai_generated:$('#final-ai').value});
  $('#upload-progress').hidden=false;$('#upload-progress').value=0;
  try{
    await new Promise((resolve,reject)=>{
      const xhr=new XMLHttpRequest();xhr.open('POST',`/api/campaigns/${encodeURIComponent(cid)}/finals/media?${params}`);xhr.timeout=660000;xhr.setRequestHeader('Content-Type','application/octet-stream');
      xhr.upload.onprogress=e=>{if(e.lengthComputable){$('#upload-progress').value=100*e.loaded/e.total;$('#upload-state').textContent='動画を転送しています…';}};
      xhr.upload.onload=()=>{$('#upload-state').textContent='転送済み · 映像の検査とMP4変換を行っています…';$('#upload-progress').removeAttribute('value');};
      xhr.onload=()=>{let data;try{data=JSON.parse(xhr.responseText);}catch{data={detail:'サーバーの応答を読み取れませんでした。'};}xhr.status>=200&&xhr.status<300?resolve(data):reject(new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail)));};
      xhr.onerror=()=>reject(new Error('通信が中断しました。再読み込みして取り込み履歴を確認してください。'));
      xhr.ontimeout=()=>reject(new Error('応答待ちを終了しました。重複取り込みを避けるため、履歴を確認してください。'));xhr.send(file);
    });
    $('#final-form').reset();$('#upload-state').textContent='取り込みました。下の動画を確認して、配信に使う版を採用してください。';await loadFinals();
  }catch(error){$('#upload-state').textContent=error.message;}
  finally{uploading=false;$('#final-upload').disabled=false;$('#campaign').disabled=busy;$('#reload').disabled=busy;$('#upload-progress').hidden=true;}
});
$('#login-form').addEventListener('submit',async e=>{
  e.preventDefault();try{await api('/api/session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:$('#login-token').value})});$('#login-token').value='';$('#login-dialog').close();await init();}catch(error){$('#login-error').textContent=error.message;}
});
async function openGeneration(sceneId){
  if(busy||uploading)return;
  blocked(true);
  try{
    await save();await loadJobs();
    if(!jobsConfigured)throw new Error('先に「接続設定と料金の扱い」を確認して、サーバー側のfal接続を有効にしてください。');
    generating={scene:structuredClone(plan.scenes.find(s=>s.id===sceneId)),revision:rev,ratio:plan.aspect_ratio,campaign:cid};
    if(!generating.scene||generating.scene.seconds<4||!Number.isInteger(generating.scene.seconds))throw new Error('Seedanceの秒数は4〜30秒の整数にしてください。');
    $('#generation-form').reset();$('#generation-prompt').textContent=generating.scene.prompt;
    $('#generation-meta').textContent=`${generating.scene.seconds}秒 · ${generating.ratio} · ${generating.scene.id}`;
    $('#generation-error').textContent='';$('#generation-dialog').showModal();
  }catch(e){message(e.message,true);}finally{blocked(false);}
}
$('#generation-close').onclick=()=>$('#generation-dialog').close();
$('#generation-form').addEventListener('submit',async e=>{
  e.preventDefault();$('#generation-submit').disabled=true;
  try{
    await api(`/api/campaigns/${generating.campaign}/scene-jobs`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      expected_revision:generating.revision,scene_id:generating.scene.id,resolution:$('#generation-resolution').value,
      generate_audio:$('#generation-audio').value==='true',take:Number($('#generation-take').value),estimated_cost_usd:Number($('#generation-estimate').value),
      external_data_consent:$('#generation-consent').checked,charge_confirmed:$('#generation-charge').checked})});
    $('#generation-dialog').close();await loadJobs();message('生成依頼を記録しました。状態は下の素材一覧で確認できます。');
  }catch(error){$('#generation-error').textContent=error.message;}finally{$('#generation-submit').disabled=false;}
});
const jobLabels={queued:'待機中',running:'生成・取得中',ready:'取得済み · 要確認',failed:'停止 · 詳細を確認',interrupted:'中断 · 再開待ち',cancelled:'開始前に取消'};
async function loadJobs(){
  clearTimeout(jobTimer);if(!cid||fetchingJobs)return;fetchingJobs=true;const current=cid;
  try{
    const data=await(await api(`/api/campaigns/${current}/scene-jobs`)).json();if(current!==cid)return;
    jobsConfigured=data.configured;$('#generation-status').textContent=jobsConfigured?'接続設定あり · 有料生成はシーンごとの確認後。実サービスでの動作・品質は別途確認が必要です。':'接続未設定 · 構成の編集・指示の出力・完成動画の取り込みはこのまま利用できます。';
    $('#scene-jobs').replaceChildren();
    for(const job of data.items){
      const card=document.createElement('article');card.className='job-card';
      const h=document.createElement('h3');h.textContent=`${job.spec.scene_id} / Take ${job.spec.take}`;
      const label=document.createElement('p');label.textContent=jobLabels[job.state]||job.state;
      const details=document.createElement('p');details.textContent=`${job.spec.input.duration}秒 · ${job.spec.input.resolution} · 見積り $${job.spec.estimated_cost_usd}`;
      card.append(h,label,details);
      if(job.spec.plan_revision!==rev){const old=document.createElement('small');old.textContent='以前の構成で依頼した素材';card.append(old);}
      if(job.error){const error=document.createElement('p');error.className='error';error.textContent=job.error;card.append(error);}
      if(job.state==='ready'){
        const video=document.createElement('video');video.src=job.media_url;video.controls=true;video.playsInline=true;video.preload='none';
        const a=document.createElement('a');a.href=job.media_url;a.textContent='素材を保存して編集に使う ↗';a.download=job.spec.scene_id+'.mp4';card.append(video,a);
      }
      const action=job.state==='queued'?'cancel':['failed','interrupted'].includes(job.state)?'resume':null;
      if(action){const button=document.createElement('button');button.type='button';button.textContent=action==='cancel'?'開始前の依頼を取り消す':'同じ依頼を再開・照合';
        button.onclick=async()=>{if(action==='resume'&&!confirm('保存された同じ依頼を再開します。送信済みの結果が不明な場合は自動で再生成しません。続けますか？'))return;button.disabled=true;
          try{await api(`/api/campaigns/${current}/scene-jobs/${job.id}/${action}`,{method:'POST'});await loadJobs();}catch(e){message(e.message,true);}finally{button.disabled=false;}};card.append(button);}
      $('#scene-jobs').append(card);
    }
    if(data.items.some(j=>['running','queued'].includes(j.state)))jobTimer=setTimeout(()=>{if(!document.hidden)loadJobs().catch(e=>message(e.message,true));},5000);
  }finally{fetchingJobs=false;}
}
$('#refresh-jobs').onclick=()=>loadJobs().catch(e=>message(e.message,true));
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&cid)loadJobs().catch(e=>message(e.message,true));});
init();

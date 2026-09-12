// No client-side API secrets. The studio uses an HttpOnly local session cookie.
import {watch, preferredLanguage, setLanguage, t} from './i18n.js';
const $ = (id) => document.getElementById(id);
const escape = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state = {config:{}, campaigns:[], current:null, tab:'film', ratio:'landscape', timer:null, integrations:[], recorded:null, recorder:null, lastSignature:''};
const labels={draft:'下書き',queued:'制作待ち',building:'制作中',awaiting_review:'構成の確認待ち',ready:'制作完了',failed:'要確認',interrupted:'中断',approved:'承認済み',submitting:'送信中',submitted:'Postiz受付済み',needs_reconciliation:'送信結果を要確認'};
const stageLabels={direction:'企画・方向性',awaiting_review:'構成の確認待ち',brief:'企画',planning:'企画',site:'LP制作',capture:'操作収録',generation:'映像生成',render:'映像編集',rendering:'映像編集',package:'梱包・検証',quality:'品質確認',ready:'制作完了'};
function toast(message){$('toast').textContent=message;$('toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').hidden=true,5500);}
function modal(id){if(!$(id).open)$(id).showModal();}
async function api(path, options={}){
  const headers=new Headers(options.headers||{});
  if(options.body && !(options.body instanceof Blob) && !(options.body instanceof ArrayBuffer)){headers.set('Content-Type','application/json');options.body=JSON.stringify(options.body);}
  const r=await fetch(path,{...options,headers,credentials:'same-origin'});
  const data=r.status===204?{}:await r.json().catch(()=>({detail:r.statusText}));
  if(!r.ok){if(r.status===401)modal('access-dialog');const message=typeof data.detail==='string'?data.detail:JSON.stringify(data.detail||data);throw new Error(message);}
  return data;
}
function output(name){return state.current?.outputs?.[name]||'';}
function updateCampaignBar(){
  $('campaign-select').innerHTML=state.campaigns.length?state.campaigns.map(c=>`<option value="${c.id}">${escape(c.brief.name)} · ${new Date(c.created*1000).toLocaleDateString()}</option>`).join(''):'<option>最初のキャンペーン</option>';
  if(state.current)$('campaign-select').value=state.current.id;
  $('campaign-state').textContent=labels[state.current?.state]||'未作成';
  $('campaign-state').className='pill '+(state.current?.state||'');
}
function renderPipeline(){
  const c=state.current,p=c?.progress||0;
  const completed=c?.state==='ready'?4:p>=82?3:p>=40?2:p>=20?1:p>8?0:-1;
  const stages=['企画・方向性','ランディングページ','操作収録','映像・パッケージ','承認・配信','実測・改善'];
  $('pipeline').innerHTML=stages.map((label,i)=>`<div class="pipeline-step ${i<completed?'done':i===completed?'current':''}"><div class="line"></div><div class="step-label"><span class="step-index">0${i+1}</span>${label}</div></div>`).join('');
  if(c?.state==='ready')document.querySelectorAll('.pipeline-step').forEach((el,i)=>{el.className='pipeline-step '+(i<4?'done':i===4?'current':'');});
}
function errorPanel(){const c=state.current;if(!['failed','interrupted'].includes(c?.state))return '';return `<div class="error-panel"><strong>制作を停止しました。公開は行っていません。</strong><p>${escape(c.error)}</p><button class="button small" id="retry-button">元の設定で再試行</button></div>`;}

const styleNames={editorial:'Editorial ／ 余白と紙の質感',spotlight:'Spotlight ／ 暗がりに、製品だけが光る',grid:'Grid ／ 方眼と小さな見出し'};
function sceneFields(scenes){
  return scenes.map((s,i)=>`<div class="scene-edit" data-scene-edit="${i}"><span class="eyebrow">0${i+1} / ${escape(s.kind.toUpperCase())}</span><label>見出し<input class="scene-title" maxlength="90" value="${escape(s.title)}"></label><label>補足<input class="scene-detail" maxlength="180" value="${escape(s.detail||'')}"></label><label>字幕 <small>空欄なら見出しを使います</small><input class="scene-caption" maxlength="120" value="${escape(s.caption||'')}" placeholder="${escape(s.title)}"></label></div>`).join('');
}
// Only what the operator actually changed is sent, so the server applies a typed
// diff instead of replacing a storyboard it validated earlier.
function collectPlanEdit(){
  const plan=state.current.plan,edit={scenes:[]};
  const concept=$('plan-concept').value.trim(),direction=$('plan-direction').value.trim();
  if(concept!==plan.concept)edit.concept=concept;
  if(direction!==plan.visual_direction)edit.visual_direction=direction;
  document.querySelectorAll('[data-scene-edit]').forEach(card=>{
    const i=Number(card.dataset.sceneEdit),scene=plan.scenes[i],change={index:i};
    const title=card.querySelector('.scene-title').value.trim();
    const detail=card.querySelector('.scene-detail').value.trim();
    const caption=card.querySelector('.scene-caption').value.trim();
    if(title!==scene.title)change.title=title;
    if(detail!==(scene.detail||''))change.detail=detail;
    if(caption!==(scene.caption||''))change.caption=caption;
    if(Object.keys(change).length>1)edit.scenes.push(change);
  });
  if(!edit.scenes.length)delete edit.scenes;
  return (edit.concept===undefined&&edit.visual_direction===undefined&&!edit.scenes)?null:edit;
}
function storyboardForm(plan,options){
  return `<div class="review-grid"><label class="span2">この映像の狙い<textarea id="plan-concept" rows="2" maxlength="300">${escape(plan.concept)}</textarea></label><label class="span2">演出方針 <small>${escape(styleNames[options?.visual_style]||options?.visual_style||'editorial')}</small><textarea id="plan-direction" rows="2" maxlength="500">${escape(plan.visual_direction)}</textarea></label></div><div class="scene-editor">${sceneFields(plan.scenes)}</div>`;
}
function renderReview(){
  const c=state.current,plan=c.plan,still=c.outputs?.['review-frame.jpg'];
  return `<section class="panel review-panel"><div class="card-heading"><h2>◫ &nbsp; 届ける前に、構成を確かめる。</h2><span class="pill">レンダリング前</span></div><p class="notice">まだ映像は書き出していません。生成AIへの依頼も、外部への送信もしていません。文言を直してから承認してください。<br>機能の主張そのものは企画で確定済みです。ここで直すのは、見出し・補足・字幕の言い回しです。</p>${still?`<img class="review-still" src="${still}" alt="収録した画面の1コマ">`:''}${storyboardForm(plan,c.options)}<div class="dialog-actions"><span>編集は制作者の文言として記録されます。</span><button class="button small" id="save-plan">下書きとして保存</button><button class="button dark" id="approve-plan">承認してレンダリング ↗</button></div><p class="error" id="review-panel-error"></p></section>`;
}
function renderRevise(){
  const c=state.current,plan=c.plan;
  return `<details class="panel revise-panel"><summary>${t('構成を直して、この素材のまま作り直す')}${c.revision?` · ${t('改訂')} ${c.revision}`:''}</summary><p class="notice">収録済みの映像をそのまま使います。再収録も、生成AIへの再依頼も行いません。作り直すと現在の動画・LP・キットは置き換わります。</p>${storyboardForm(plan,c.options)}<div class="dialog-actions"><span>投稿済みの内容は変わりません。</span><button class="button dark" id="revise-plan">この内容で作り直す ↻</button></div><p class="error" id="revise-error"></p></details>`;
}
function renderFilm(){
  const c=state.current,ready=c?.state==='ready',name=c?.brief.name||'Your next good thing';
  if(c?.state==='awaiting_review'&&c.plan)return renderReview();
  const scenes=c?.plan?.scenes||[{kind:'hook',title:'心を動かす、最初の3秒。'},{kind:'proof',title:'本当に動くところを見せる。'},{kind:'cta',title:'次の一歩につなげる。'}];
  const warnings=c?.qa?.warnings||[];
  return `<div class="workbench-grid"><div><section class="studio-card"><div class="card-heading"><h2>◫ &nbsp; プロダクトフィルム <span class="kicker">/ ${ready?'READY TO REVIEW':'YOUR NEXT STORY'}</span></h2><div class="ratio-switch"><button data-ratio="landscape" class="${state.ratio==='landscape'?'active':''}">16 : 9</button><button data-ratio="portrait" class="${state.ratio==='portrait'?'active':''}">9 : 16</button></div></div><div class="player ${state.ratio==='portrait'?'portrait':''}">${ready?`<video id="film-player" controls playsinline preload="metadata" poster="${output(state.ratio+'.jpg')}" src="${output(state.ratio+'.mp4')}"></video>`:`<div class="empty-preview"><span class="preview-label">${escape(name.toUpperCase())} / PRODUCT FILM</span><h2>${escape(c?.brief.tagline||'いいものを、\n見過ごされないものに。').replace('\n','<br>')}</h2><p>${c?'企画から実ファイルを制作しています。':'映像も、サイトも、その先の広がりも。'}</p><i class="preview-ring"></i><b class="preview-dot"></b><span class="empty-play">${c?'レンダリング完了後に実際の動画を表示します。':'未作成 · サンプルで、制作の一連を試す ↗'}</span></div>`}${['queued','building'].includes(c?.state)?`<div class="rendering-status"><span><i class="spinner"></i>${escape(stageLabels[c.stage]||c.stage)}</span><b>${c.progress}%</b></div>`:''}</div><div class="timeline"><div class="timeline-label"><span>STORYBOARD / ${scenes.length} SCENES</span><span>${ready?'RENDERED IN 24 FPS':'CONCEPT → PROOF → ACTION'}</span></div><div class="timeline-track">${scenes.map((s,i)=>`<button class="clip" data-scene="${i}" ${!ready?'disabled':''}><span>0${i+1} / ${escape(s.kind.toUpperCase())}</span><b>${escape(s.title)}</b></button>`).join('')}</div></div><div class="card-bottom"><span>${ready?'実ファイル生成済み · 公開前に映像を確認してください。':'ローカル制作には生成AIのAPIキーは不要です。'}</span>${ready?`<a class="button small" href="${output('launch-kit.zip')}" download>制作キットを書き出す ↓</a>`:'<button class="button small" data-new>最初の企画をつくる ↗</button>'}</div></section>${ready&&c?.plan?renderRevise():''}<section class="next-strip"><div><span class="eyebrow">THE NEXT RIGHT STEP</span><h3>${ready?'いい映像に、いい入口を。':'ひとつの企画、いくつもの届け方。'}</h3><p>${ready?'同じトーンのLPと、投稿原稿もできています。':'まずは内蔵サンプルを動かして、実際の制作物を確認。'}</p></div><button class="button small" data-go="${ready?'site':'distribution'}"><span>${ready?'LPを見る':'配信のしくみ'}</span> ↗</button></section></div><aside class="details-column"><section class="detail-card"><span class="eyebrow">CREATIVE DIRECTION</span><h3>${escape(c?.plan?.concept||'伝わる。\nそのあとに、動きたくなる。').replace('\n','<br>')}</h3><p>${escape(c?.plan?.visual_direction||'華やかさだけで終わらせず、実際の機能を、使う場面へつなげます。')}</p><div class="detail-row"><span>プロダクト</span><b>${escape(c?.brief.name||'未設定')}</b></div><div class="detail-row"><span>映像の入力</span><b>${escape(c?.options?.capture_mode==='sample'?'内蔵の実動作アプリ':c?.options?.capture_mode==='url'?'Playwright 自動収録':c?.options?.capture_mode==='upload'?'収録・アップロード':'機能紹介アニメーション')}</b></div><div class="detail-row"><span>生成エンジン</span><b>${escape(c?.options?.film_provider||'local')} / FFmpeg</b></div><div class="detail-row"><span>アクセント</span><span class="swatches"><i style="background:${escape(c?.brief.accent||'#ed6847')}"></i><i style="background:#293d37"></i><i style="background:#dce4d2"></i><i style="background:#f6f2e9"></i></span></div></section><section class="detail-card"><span class="eyebrow">QUALITY & TRUST</span><div class="quality-row"><span class="checkmark">✓</span><span>確認済みの機能だけを紹介</span></div><div class="quality-row"><span class="checkmark">✓</span><span>APIキーはブラウザに渡さない</span></div><div class="quality-row"><span class="checkmark">✓</span><span>外部投稿には別途、明示承認が必要</span></div>${warnings.map(w=>`<div class="quality-row"><span>↳</span><span>${escape(w)}</span></div>`).join('')}</section></aside></div>`;
}
function empty(message){return `<section class="panel empty-panel"><div><span class="eyebrow">ONE THING AT A TIME.</span><h2>${escape(message)}</h2><p>企画を作成するか、内蔵サンプルでローカル制作をお試しください。外部への投稿は行いません。</p><button class="button" data-new>企画をつくる ↗</button></div></section>`;}
function renderSite(){
  if(state.current?.state!=='ready')return empty('LPは、映像と一緒に仕上がります。');
  const c=state.current,configured=state.config.deploy_target_configured;
  const deployment=`<section class="panel deploy-panel"><div class="card-heading"><h3>公開先へ置く</h3>${configured?`<button class="button small" id="deploy-preview">書き込む内容を確認 ↻</button>`:''}</div>${configured?`<p class="notice">自分が公開に使っているディレクトリへ、生成した5つのファイルだけをコピーします。ほかのファイルは消しません。アップロードやDNSの設定は行いません。${c.released?'':'<br><b>このキャンペーンはまだ保留中です。公開可能にしてから配信してください。</b>'}</p><div id="deploy-body"></div>`:`<p class="notice">配信先が未設定です。<code>SITE_DEPLOY_DIR</code> に、自分が公開に使っているディレクトリを設定して再起動してください。ホスティングのAPI連携は実装していません。</p>`}</section>`;
  return `<section class="panel"><div class="card-heading"><h2>▧ &nbsp; ${escape(c.brief.name)} / Landing page</h2><div class="links-row"><a class="button small" target="_blank" rel="noopener" href="${output('site/index.html')}">別タブで見る ↗</a><a class="button small" href="${output('launch-kit.zip')}">HTMLを含むキット ↓</a></div></div><iframe class="site-frame" title="生成したランディングページ" sandbox="allow-scripts allow-same-origin" src="${output('site/index.html')}"></iframe><div class="card-bottom"><span>レスポンシブHTML・CSS・JS / 自動公開は行っていません。</span></div></section>`+deployment;
}
function releaseBar(){
  const c=state.current,released=!!c.released;
  return `<section class="panel release-bar ${released?'released':''}"><div><span class="eyebrow">${released?'RELEASED FOR PUBLISHING':'HELD ON THIS MACHINE'}</span><h3>${released?'このキャンペーンは、送信できる状態です。':'まだ、何も外に出せません。'}</h3><p>${released?'投稿ごとの承認は、引き続き別に必要です。':'映像が完成しても、公開の判断は別の操作です。準備ができたら公開可能にしてください。'}</p></div><button class="button ${released?'small':'dark'}" id="${released?'hold-campaign':'release-campaign'}">${released?'保留に戻す':'公開可能にする ↗'}</button></section>`;
}
function reconcileRow(p){
  const remote=p.remote_state?`<span class="pill remote-${escape(p.remote_state)}">${escape({published:'SNSで公開済み',queued:'Postizで待機中',failed:'失敗',draft:'下書き',absent:'見つからない',unknown:'不明'}[p.remote_state]||p.remote_state)}</span>`:'';
  const link=p.remote_url?`<a class="button small" href="${escape(p.remote_url,true)}" target="_blank" rel="noopener">投稿を見る ↗</a>`:'';
  const fix=p.state==='needs_reconciliation'?`<button class="button small dark" data-reconcile="${escape(p.id)}">突合する ↗</button>`:'';
  return `<div class="publication-row"><span>${escape(p.payload.channel)} · ${escape(p.payload.integration_id)}</span><span class="row-end"><span class="pill">${escape(labels[p.state]||p.state)}</span>${remote}${link}${fix}</span></div>`;
}
function renderDistribution(){
  if(state.current?.state!=='ready')return empty('できあがったら、届け方を選ぶ。');
  const posts=state.current.posts?.posts||state.current.posts||[];
  const items=Array.isArray(posts)?posts:Object.values(posts);
  const pacing=t('同じSNSへは{gap}分以上あけ、1日{max}件までにしています。')
    .replace('{gap}',state.config.min_post_gap_minutes||30)
    .replace('{max}',state.config.max_posts_per_channel_per_day||3);
  return releaseBar()+`<section class="panel distribution-heading"><div class="card-heading"><h2>↗ &nbsp; 配信は、最後の承認から。</h2><div class="links-row"><button class="button small" id="load-integrations">投稿先を読み込む ↻</button><button class="button small" id="check-remote">実状態を確認 ↻</button></div></div><div class="notice" style="margin:18px">${state.config.postiz?'Postiz連携あり。投稿原稿・動画・アカウントを確認してから、送信してください。':'Postizは未接続です。原稿のコピーと送信データのプレビューは使用できます。実投稿には接続設定が必要です。'}<br>予約はPostizに委任します。「受付済み」は各SNSでの公開成功を意味しません。<br>${pacing}</div></section><div class="post-grid">${items.map((p,i)=>`<section class="post-card" data-post="${i}"><div class="post-heading"><strong>${escape(p.channel.toUpperCase())}</strong><span class="pill">承認待ち</span></div><textarea class="post-content" rows="9">${escape(p.content)}</textarea><label>投稿先 integration ID<input class="integration-id" list="accounts-list" placeholder="PostizのアカウントID"></label><label>予約日時（空欄は今すぐ）<input class="schedule-at" type="datetime-local"></label><details class="advanced"><summary>メディア・SNS固有設定</summary><label>動画<select class="media"><option value="landscape.mp4" ${p.media==='landscape.mp4'?'selected':''}>横長 16:9</option><option value="portrait.mp4" ${p.media==='portrait.mp4'?'selected':''}>縦長 9:16</option></select></label><label>プラットフォーム設定（JSON）<textarea class="platform-settings" rows="3">{}</textarea></label></details><div class="post-actions"><button class="button small" data-copy="${i}">原稿をコピー</button>${(p.hook_variants||[]).length>1?`<button class="button small" data-variant="${i}">別の切り口にする ↺</button>`:''}<button class="button small dark" data-review="${i}">内容を確認 ↗</button></div></section>`).join('')}</div><datalist id="accounts-list">${state.integrations.map(a=>`<option value="${escape(a.id)}">${escape(a.name||a.identifier||a.id)}</option>`).join('')}</datalist><section class="panel" style="padding:22px;margin-top:20px"><span class="eyebrow">PUBLICATION HISTORY</span>${state.current.publications?.length?state.current.publications.map(reconcileRow).join(''):'<p class="notice">送信履歴はありません。外部への投稿はまだ行っていません。</p>'}</section>`;
}
function renderResults(){
  if(!state.current)return empty('数字がないときは、ないと伝えます。');
  const m=state.current.metrics||{};
  return `<div class="metrics-grid">${[['LPの表示',m.page_views??0,'イベント数 / ユニーク訪問者ではありません'],['CTAクリック',m.cta_clicks??0,'実際に送信された計測イベント'],['登録完了',m.signups??0,'自社バックエンドで確認した登録のみ']].map(([title,value,note])=>`<section class="metric-card"><span>${title}</span><strong>${value}</strong><small>${note}</small></section>`).join('')}</div><section class="panel" style="padding:28px"><span class="eyebrow">HONEST SIGNALS, BETTER DECISIONS.</span><h2>まだ知らないことは、埋めない。</h2><p class="notice">${escape(m.recommendation||'実測値を待っています。')}<br><span>SNSインプレッション：未取得。未取得の値は推計で補いません。</span>${state.config.tracking?'計測接続が設定されています。':'LP計測は未設定です。PUBLIC_TRACKING_BASEを設定して新しく制作してください。'}</p><button class="button small" id="analytics-button">Postizの実測値を取得 ↻</button><pre id="analytics-output" hidden></pre></section>`;
}
function renderActivity(){if(!state.current)return empty('すべての工程に、足あとを。');return `<section class="panel" style="padding:25px"><span class="eyebrow">ACTIVITY / ${state.current.id}</span><h2>何が、どこまで進んだか。</h2>${(state.current.events||[]).map(e=>`<div class="event"><time>${new Date(e.created*1000).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}</time><span class="pill">${escape(e.kind)}</span><p>${escape(e.message)}</p></div>`).join('')||'<p class="notice">制作を開始すると記録されます。</p>'}</section>`;}
function render(){
  renderPipeline();updateCampaignBar();document.querySelectorAll('#nav button').forEach(b=>b.classList.toggle('active',b.dataset.tab===state.tab));
  $('workbench').innerHTML=errorPanel()+({film:renderFilm,site:renderSite,distribution:renderDistribution,results:renderResults,activity:renderActivity}[state.tab])();
  $('retry-button')?.addEventListener('click',async()=>{try{await api(`/api/campaigns/${state.current.id}/build`,{method:'POST',body:state.current.options});await refresh(true);}catch(e){toast(e.message);}});
  $('load-integrations')?.addEventListener('click',loadIntegrations);
  $('save-plan')?.addEventListener('click',()=>savePlan(false));
  $('approve-plan')?.addEventListener('click',()=>savePlan(true));
  $('revise-plan')?.addEventListener('click',revisePlan);
  $('release-campaign')?.addEventListener('click',()=>setRelease(true));
  $('hold-campaign')?.addEventListener('click',()=>setRelease(false));
  $('check-remote')?.addEventListener('click',checkRemoteStates);
  $('deploy-preview')?.addEventListener('click',previewDeployment);
  $('analytics-button')?.addEventListener('click',async()=>{try{const d=await api(`/api/campaigns/${state.current.id}/social-analytics`);$('analytics-output').hidden=false;$('analytics-output').textContent=JSON.stringify(d,null,2);}catch(e){toast(e.message);}});
}

async function savePlan(approve){
  const error=$('review-panel-error');error.textContent='';
  const buttons=['save-plan','approve-plan'].map($);buttons.forEach(b=>b&&(b.disabled=true));
  try{
    const edit=collectPlanEdit();
    if(edit)await api(`/api/campaigns/${state.current.id}/plan`,{method:'PATCH',body:edit});
    if(approve){await api(`/api/campaigns/${state.current.id}/render`,{method:'POST'});toast('構成を承認しました。レンダリングを開始します。');}
    else toast(edit?'構成を保存しました。':'変更はありません。');
    await refresh(true);
  }catch(e){error.textContent=e.message;buttons.forEach(b=>b&&(b.disabled=false));}
}
async function revisePlan(){
  const error=$('revise-error');error.textContent='';
  const button=$('revise-plan');button.disabled=true;
  try{
    const edit=collectPlanEdit();
    await api(`/api/campaigns/${state.current.id}/revise`,{method:'POST',...(edit?{body:edit}:{})});
    toast('同じ素材のまま、作り直しています。');
    await refresh(true);
  }catch(e){error.textContent=e.message;button.disabled=false;}
}

async function setRelease(release){
  try{
    await api(`/api/campaigns/${state.current.id}/${release?'release':'hold'}`,{method:'POST',...(release?{body:{confirmed:true}}:{})});
    toast(release?'公開可能にしました。投稿ごとの承認は引き続き必要です。':'保留に戻しました。未送信の投稿は送信できません。');
    await refresh(true);
  }catch(e){toast(e.message);}
}
async function checkRemoteStates(){
  const button=$('check-remote');button.disabled=true;
  try{
    const r=await api(`/api/campaigns/${state.current.id}/publication-states`);
    if(!r.items.length){toast('確認できる送信記録がまだありません。');return;}
    const absent=r.items.filter(i=>i.remote_state==='absent').length;
    toast(`${r.items.length}${t('件を確認しました。')}${absent?`${absent}${t('件はPostizに見つかりません。')}`:''}`);
    await refresh(true);
  }catch(e){toast(e.message);}finally{button.disabled=false;}
}
// An uncertain send is resolved by a person looking, never by trying again blindly.
async function reconcile(pid){
  $('review-body').innerHTML='<p class="notice">Postizの記録を確認しています…</p>';modal('review-dialog');
  let found;
  try{found=await api(`/api/publications/${pid}/candidates`);}
  catch(e){$('review-body').innerHTML=`<p class="error">${escape(e.message)}</p>`;return;}
  const rows=(found.exact?[found.exact]:found.candidates).map(post=>`<label class="check"><input type="radio" name="remote-choice" value="${escape(post.id,true)}"><span><b>${escape(post.id)}</b> · ${escape(post.state||'')}<br><small>${escape(String(post.content||'').slice(0,90))}</small></span></label>`).join('');
  $('review-body').innerHTML=`<span class="eyebrow">WHAT ACTUALLY EXISTS</span><h3>送信の結果を、目で確かめる。</h3><p class="notice">送信がタイムアウトしても、投稿が作られていないとは限りません。自動では再送しません。${escape(found.window?.[0]||'')} 〜 ${escape(found.window?.[1]||'')}${t('のPostizの記録です。')}</p>${found.exact?'<p>送信時のIDと一致する投稿が見つかりました。</p>':rows?'<p>同じアカウント・同じ書き出しの投稿が見つかりました。該当するものを選んでください。</p>':'<p>この期間に、該当しそうな投稿は見つかりませんでした。</p>'}${rows||''}<label>Postizの投稿ID（手元で確認した場合）<input id="remote-id" placeholder="例: cmxxxx"></label><label>メモ<input id="remote-note" maxlength="400" placeholder="どこで確認したか"></label><div class="dialog-actions"><button class="button small" id="mark-absent">投稿は作られていない</button><button class="button dark" id="mark-published">この投稿として記録する ↗</button></div><p class="error" id="reconcile-error"></p>`;
  const chosen=()=>document.querySelector('input[name="remote-choice"]:checked')?.value||$('remote-id').value.trim();
  $('mark-published').onclick=async()=>{
    try{
      await api(`/api/publications/${pid}/reconcile`,{method:'POST',body:{resolution:'published',remote_id:chosen(),note:$('remote-note').value}});
      $('review-dialog').close();toast('実在する投稿として記録しました。');await refresh(true);
    }catch(e){$('reconcile-error').textContent=e.message;}
  };
  $('mark-absent').onclick=async()=>{
    try{
      await api(`/api/publications/${pid}/reconcile`,{method:'POST',body:{resolution:'not_published',note:$('remote-note').value}});
      $('review-dialog').close();toast('未作成として記録しました。承認済みに戻したので、必要なら送信し直せます。');await refresh(true);
    }catch(e){$('reconcile-error').textContent=e.message;}
  };
}

const deployLabels={adds:'新しく置く',replaces:'置き換える',unchanged:'変更なし'};
async function previewDeployment(){
  const body=$('deploy-body');body.innerHTML='<p class="notice">確認しています…</p>';
  let preview;
  try{preview=await api(`/api/campaigns/${state.current.id}/deployment-preview`);}
  catch(e){body.innerHTML=`<p class="error">${escape(e.message)}</p>`;return;}
  const rows=preview.files.map(f=>`<div class="publication-row"><span>${escape(f.name)}<small> · ${(f.bytes/1024).toFixed(0)} KB</small></span><span class="pill ${escape(f.status)}">${escape(deployLabels[f.status]||f.status)}</span></div>`).join('');
  body.innerHTML=`<p class="deploy-target">書き込み先：<b>${escape(preview.target)}</b></p>${rows}<p class="notice">${t('このディレクトリの他のファイル（')}${preview.left_untouched.length?escape(preview.left_untouched.slice(0,6).join(', ')):t('なし')}${preview.left_untouched.length>6?t(' ほか'):''}${t('）はそのまま残ります。')}</p><div class="dialog-actions"><span>承認は、いま確認したこの内容に対してのみ有効です。</span><button class="button dark" id="deploy-confirm" ${state.current.released?'':'disabled'}>この内容で書き出す ↗</button></div><p class="error" id="deploy-error"></p>`;
  $('deploy-confirm').onclick=async()=>{
    $('deploy-confirm').disabled=true;
    try{
      const r=await api(`/api/campaigns/${state.current.id}/deploy`,{method:'POST',body:{confirmed:true,fingerprint:preview.fingerprint}});
      toast(`${r.written.length}個のファイルを ${r.target} へ書き出しました。`);
      await previewDeployment();
    }catch(e){$('deploy-error').textContent=e.message;$('deploy-confirm').disabled=false;}
  };
}
async function loadIntegrations(){try{const r=await api('/api/integrations');state.integrations=Array.isArray(r.items)?r.items:[];const d=$('accounts-list');if(d)d.innerHTML=state.integrations.map(a=>`<option value="${escape(a.id)}">${escape(a.name||a.id)}</option>`).join('');toast(r.connected?`${state.integrations.length}${t('件の投稿先を取得しました。')}`:t('Postizの環境変数を設定して再起動してください。'));}catch(e){toast(e.message);}}
async function refresh(force=false){
  clearTimeout(state.timer);
  if(!state.current)return;
  const c=await api('/api/campaigns/'+state.current.id);state.current=c;
  const signature=JSON.stringify([c.id,c.state,c.progress,c.stage,c.revision,c.publications?.map(p=>p.state),c.metrics]);
  if(force||signature!==state.lastSignature){state.lastSignature=signature;render();}
  if(['queued','building'].includes(c.state))state.timer=setTimeout(()=>refresh().catch(e=>toast(e.message)),1500);
}
async function initialize(){state.config=await api('/api/config');state.campaigns=await api('/api/campaigns');if(state.campaigns.length){state.current=state.campaigns[0];await refresh(true);}else render();}
function connectionStep(done,title,detail,extra=''){
  return `<div class="wizard-step ${done?'done':''}"><span class="step-mark">${done?'✓':'·'}</span><div><b>${title}</b><p>${detail}</p>${extra}</div></div>`;
}
function settings(){
  const c=state.config,accounts=state.integrations;
  const requirements=Object.entries(c.channel_settings||{}).map(([channel,keys])=>`<div class="setting-row"><span>${escape(channel.toUpperCase())}</span><b>${escape(keys.join(', '))}</b></div>`).join('');
  $('settings-body').innerHTML=`<p>キーはサーバーの .env で設定して再起動します。ブラウザにAPIキーは保存しません。</p>
    <div class="wizard">
      ${connectionStep(c.postiz,'1. PostizにSNSを接続する','SNSのOAuthはPostiz側で行います。Launchloomは、Postizが接続済みのアカウントにだけ投稿します。','<pre>POSTIZ_BASE_URL=https://api.postiz.com/public/v1\nPOSTIZ_API_KEY=...</pre>')}
      ${connectionStep(accounts.length>0,'2. 接続を確かめる',accounts.length?`${accounts.length}${t('件の投稿先が見つかりました：')}${accounts.map(a=>escape(a.name||a.id)).join('、')}`:t('「投稿先を読み込む」で、Postizが持っているアカウントを取得します。'),'<button class="button small" id="wizard-integrations">投稿先を読み込む ↻</button>')}
      ${connectionStep(c.live_publish,'3. 実投稿を許可する','既定では送信しません。<code>ENABLE_LIVE_PUBLISH=1</code> にして再起動すると、承認した投稿だけ送信できます。')}
      ${connectionStep(!!state.current?.released,'4. キャンペーンを公開可能にする','完成とは別の判断です。配信タブで公開可能にしてから、投稿ごとに承認します。')}
    </div>
    <span class="eyebrow">CHANNELS THAT NEED EXTRA SETTINGS</span>${requirements}
    <span class="eyebrow">STATUS</span>
    ${[['ローカル制作',true],['fal 映像生成',c.fal],['ComfyUI',c.comfy],['企画LLM',c.llm],['Postiz',c.postiz],['外部投稿の実行許可',c.live_publish],['LP配信先',c.deploy_target_configured],['LP計測',c.tracking],['Chromium sandbox',c.capture_sandbox]].map(([k,v])=>`<div class="setting-row"><span>${k}</span><b>${v?'有効':'未設定 / 無効'}</b></div>`).join('')}
    <p>無料のローカル制作は、APIキーなしで動作します。非公開データを含む本番環境の収録は避けてください。</p>`;
  $('wizard-integrations').onclick=async()=>{await loadIntegrations();settings();};
  modal('settings-dialog');
}
function newCampaign(){modal('create-dialog');}
async function review(index){
  const cards=document.querySelectorAll('[data-post]'),card=cards[index];
  const items=state.current.posts.posts||state.current.posts,p=items[index];
  const schedule=card.querySelector('.schedule-at').value;
  const payload={channel:p.channel,content:card.querySelector('.post-content').value,integration_id:card.querySelector('.integration-id').value.trim()||'dry-run-only',media:card.querySelector('.media').value,schedule_at:schedule?new Date(schedule).toISOString():'',settings:JSON.parse(card.querySelector('.platform-settings').value||'{}')};
  const pub=await api(`/api/campaigns/${state.current.id}/publications`,{method:'POST',body:payload});
  const live=state.config.live_publish&&state.config.postiz&&payload.integration_id!=='dry-run-only';
  $('review-body').innerHTML=`<video class="review-video" controls playsinline src="${output(payload.media)}"></video><div class="review-copy">${escape(payload.content)}</div><p>${t('投稿先')}：${escape(payload.channel)} / ${escape(payload.integration_id)}<br>${t('実行')}：${escape(schedule||t('今すぐ（明示送信した時点）'))}</p><p class="fingerprint">承認対象 SHA-256<br>${pub.fingerprint}</p><label class="check"><input type="checkbox" id="review-content">原稿・機能の主張・実際の動画を確認しました。</label><label class="check"><input type="checkbox" id="review-rights">映像・音声の利用権を確認しました。</label><label class="check"><input type="checkbox" id="review-account">このアカウントへの公開を許可します。</label><div class="dialog-actions"><button class="button small" id="dry-run">送信データを見る（送信なし）</button><button class="button dark" id="submit-publication" ${!live?'disabled':''}><span>${schedule?'承認して予約':'承認して投稿'}</span> ↗</button></div>${!live?'<p class="notice">実投稿は無効です。接続設定・有効な投稿先ID・明示的な実行許可が必要です。</p>':''}<pre id="dry-run-output" hidden></pre><p class="error" id="review-error"></p>`;
  modal('review-dialog');
  $('dry-run').onclick=async()=>{try{const r=await api(`/api/publications/${pub.id}/dry-run`);$('dry-run-output').hidden=false;$('dry-run-output').textContent=JSON.stringify(r,null,2);}catch(e){$('review-error').textContent=e.message;}};
  $('submit-publication').onclick=async()=>{
    if(!['review-content','review-rights','review-account'].every(id=>$(id).checked)){$('review-error').textContent='3つの確認項目を確認してください。';return;}
    $('submit-publication').disabled=true;
    try{await api(`/api/publications/${pub.id}/approve`,{method:'POST',body:{fingerprint:pub.fingerprint,content_reviewed:true,rights_confirmed:true,account_authorized:true}});await api(`/api/publications/${pub.id}/submit`,{method:'POST'});$('review-dialog').close();toast('Postizが受け付けました。実際の公開結果はPostiz側でも確認してください。');await refresh(true);}catch(e){$('review-error').textContent=e.message;/* No automatic retry after an uncertain send. */}
  };
}
document.addEventListener('click',async(event)=>{
  const b=event.target.closest('button');if(!b)return;
  if(b.dataset.close)$(b.dataset.close).close();
  if(b.dataset.new!==undefined)newCampaign();
  if(b.dataset.tab||b.dataset.go){state.tab=b.dataset.tab||b.dataset.go;render();}
  if(b.dataset.ratio){state.ratio=b.dataset.ratio;render();}
  if(b.dataset.scene!==undefined){const v=$('film-player');if(v&&Number.isFinite(v.duration)){const n=state.current.plan.scenes.length,i=Number(b.dataset.scene);v.currentTime=i===0?0:i===n-1?Math.max(0,v.duration-3):3+(i-1)*(v.duration-6)/(n-2);v.play().catch(()=>{});}}
  if(b.dataset.copy!==undefined){const content=document.querySelectorAll('[data-post]')[Number(b.dataset.copy)].querySelector('.post-content').value;try{await navigator.clipboard.writeText(content);toast('原稿をコピーしました。');}catch{toast('ブラウザがコピーを許可していません。原稿を選択してコピーしてください。');}}
  if(b.dataset.review!==undefined){b.disabled=true;try{await review(Number(b.dataset.review));}catch(e){toast(e.message);}finally{b.disabled=false;}}
  if(b.dataset.reconcile){try{await reconcile(b.dataset.reconcile);}catch(e){toast(e.message);}}
  if(b.dataset.variant!==undefined){
    // Swap in the alternate hook the plan already proposed; the text stays editable.
    const index=Number(b.dataset.variant),items=state.current.posts.posts||state.current.posts,post=items[index];
    const field=document.querySelectorAll('[data-post]')[index].querySelector('.post-content');
    const hooks=post.hook_variants||[];
    const current=hooks.findIndex(h=>field.value.startsWith(h));
    const next=hooks[(current+1+hooks.length)%hooks.length];
    field.value=hooks.length&&current>=0?field.value.replace(hooks[current],next):next+'\n\n'+field.value;
    toast('切り口を差し替えました。予約時刻をずらして別バージョンとして出せます。');
  }
});
for(const id of ['new-button','new-side'])$(id).onclick=newCampaign;
for(const id of ['settings-button','connect-button'])$(id).onclick=settings;
$('campaign-select').onchange=async(e)=>{state.current=state.campaigns.find(c=>c.id===e.target.value);try{await refresh(true);}catch(err){toast(err.message);}};
$('demo-button').onclick=async()=>{const b=$('demo-button');b.disabled=true;try{const c=await api('/api/demo?language='+preferredLanguage(),{method:'POST'});state.campaigns.unshift(c);state.current=c;state.tab='film';await refresh(true);}catch(e){toast(e.message);}finally{b.disabled=false;}};
$('access-form').onsubmit=async(e)=>{e.preventDefault();try{await api('/api/session',{method:'POST',body:{token:$('access-token').value}});$('access-token').value='';$('access-dialog').close();await initialize();}catch(err){$('access-error').textContent=err.message;}};
$('capture-mode').onchange=()=>{const mode=$('capture-mode').value;$('url-options').hidden=mode!=='url';$('upload-options').hidden=mode!=='upload';$('trim-options').hidden=mode==='none';};
$('record-button').onclick=async()=>{
  if(state.recorder?.state==='recording'){state.recorder.stop();return;}
  try{
    if(!navigator.mediaDevices?.getDisplayMedia)throw new Error('画面収録は対応するデスクトップブラウザのlocalhost/HTTPSで使用してください。');
    const stream=await navigator.mediaDevices.getDisplayMedia({video:{frameRate:30},audio:false});
    const mime=['video/webm;codecs=vp9','video/webm;codecs=vp8','video/webm'].find(t=>MediaRecorder.isTypeSupported(t));
    if(!mime){stream.getTracks().forEach(t=>t.stop());throw new Error('このブラウザではWebM画面収録を利用できません。動画アップロードを使用してください。');}
    const recorder=new MediaRecorder(stream,{mimeType:mime,videoBitsPerSecond:3000000}),parts=[];state.recorder=recorder;
    recorder.ondataavailable=e=>{if(e.data.size)parts.push(e.data);};
    const stop=()=>{if(recorder.state==='recording')recorder.stop();};
    const timer=setTimeout(stop,290000);
    recorder.onstop=()=>{clearTimeout(timer);stream.getTracks().forEach(t=>t.stop());state.recorded=new Blob(parts,{type:mime});$('record-button').textContent='● もう一度収録する';$('record-state').textContent=`収録完了 / ${(state.recorded.size/1048576).toFixed(1)} MB · 制作開始時に使用`;state.recorder=null;};
    stream.getVideoTracks()[0].onended=stop;recorder.start(1000);$('record-button').textContent='■ 収録を停止';$('record-state').textContent='画面収録中です。最大約5分で自動停止します。';
  }catch(e){toast(e.message);}
};
$('create-form').onsubmit=async(e)=>{
  e.preventDefault();const form=e.currentTarget,f=new FormData(form),str=k=>String(f.get(k)||'').trim(),flag=k=>f.get(k)==='on';$('create-submit').disabled=true;$('create-error').textContent='';
  try{
    if(state.recorder)throw new Error('画面収録を停止してから制作してください。');
    const features=str('features').split('\n').filter(Boolean).map(line=>{const [title,detail,evidence,...extra]=line.split('|').map(s=>s.trim());if(!title||!detail||!evidence||extra.length)throw new Error('機能は「機能名 | 説明 | 根拠」の3項目で入力してください。');return{title,detail,evidence,approved:true};});
    const capture=$('capture-file').files[0]||state.recorded,audio=$('audio-file').files[0],narration=$('narration-file').files[0],mode=str('capture_mode');
    if((mode==='upload'||audio||narration)&&!flag('media_rights'))throw new Error('使用する映像・音声の権利を確認してください。');
    if(mode==='upload'&&!capture)throw new Error('操作動画を選択するか、画面を収録してください。');
    const options={capture_mode:mode,capture_url:str('capture_url'),steps:JSON.parse(str('steps')||'[]'),redact_selectors:str('redactions').split('\n').filter(Boolean),staging_confirmed:flag('staging_confirmed'),allow_site_writes:flag('allow_site_writes'),film_provider:str('film_provider'),provider_input:JSON.parse(str('provider_input')||'{}'),estimated_cost_usd:Number(str('estimated_cost_usd')||0),external_data_consent:flag('external_data_consent'),llm_plan:flag('llm_plan'),quality:str('quality'),visual_style:str('visual_style')||'editorial',review_plan:flag('review_plan'),capture_events:mode==='upload'?JSON.parse(str('capture_events')||'[]'):[],capture_start:mode==='none'?0:Number(str('capture_start')||0),capture_length:mode==='none'?0:Number(str('capture_length')||0)};
    if(mode==='url'&&(!options.capture_url||!options.staging_confirmed))throw new Error('収録URLとテスト環境の確認が必要です。');
    if((options.film_provider!=='local'||options.llm_plan)&&!options.external_data_consent)throw new Error('選択した外部Providerへの送信許可が必要です。');
    const channels=f.getAll('channels');if(!channels.length)throw new Error('SNSを1つ以上選択してください。');
    const brief={channels,goal:str('goal'),name:str('name'),audience:str('audience'),tagline:str('tagline'),description:str('description'),product_url:str('product_url'),features,accent:str('accent'),language:str('language')};
    const c=await api('/api/campaigns',{method:'POST',body:brief});
    for(const [kind,file] of [['capture',mode==='upload'?capture:null],['audio',audio],['narration',narration]])if(file)await api(`/api/campaigns/${c.id}/media?kind=${kind}&rights_confirmed=true`,{method:'POST',body:file,headers:{'Content-Type':'application/octet-stream'}});
    await api(`/api/campaigns/${c.id}/build`,{method:'POST',body:options});state.campaigns.unshift(c);state.current=c;state.tab='film';$('create-dialog').close();state.recorded=null;form.reset();$('capture-mode').onchange();await refresh(true);
  }catch(err){$('create-error').textContent=err.message;}finally{$('create-submit').disabled=false;}
};
// The studio is written in Japanese; this translates what it renders, including
// anything a dialog fills in later. See web/i18n.js.
watch();
// Two letters, so the label never competes with the status text beside it, and
// never goes through the translation table itself.
$('language-toggle').textContent=preferredLanguage()==='ja'?'EN':'JA';
$('language-toggle').onclick=()=>setLanguage(preferredLanguage()==='ja'?'en':'ja');
render();initialize().catch(e=>{if(!$('access-dialog').open)toast(e.message);});

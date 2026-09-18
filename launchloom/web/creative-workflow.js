// Optional workflows share the editor's current version and explicit consent.
// Untrusted model text is displayed only with textContent, never as HTML/code.
export function mountCreativeWorkflow({state, api, notice, applySaved, render, t}) {
  const $ = (id) => document.getElementById(id);
  let config = null, configKey = '', proposal = null, working = false, requestId = 0, reviewKey = '';
  const endpoint = (cid) => `/api/campaigns/${encodeURIComponent(cid)}`;
  const message = (text) => { $('workflow-status').textContent = text; };
  function item(tag, text) { const node = document.createElement(tag); node.textContent = text; return node; }
  function refs(s) { return {expected_revision:s.data.revision, production_revision:s.data.production_revision}; }
  function valid(s) { return !!s.spec && !s.dirty && !s.pending && !s.data.derived && !s.data.source_changed; }
  function currentFilm(s) { return valid(s) && s.job?.state === 'ready' && s.job.scene_id === null && s.job.revision === s.data.revision; }
  function present(value) {
    proposal = value; $('proposal').hidden = false; $('proposal-reviewed').checked = false;
    $('proposal-summary').textContent = value.summary;
    $('proposal-changes').replaceChildren();
    for (const change of value.changes) {
      const line = item('article','');
      line.append(item('strong', change.target), item('del', JSON.stringify(change.before)), item('ins', JSON.stringify(change.after)));
      $('proposal-changes').append(line);
    }
    const notes = [...(value.warnings || [])];
    for (const finding of value.report?.findings || []) notes.push(`${finding.scene_id}: ${finding.message}`);
    if (value.report?.unresolved?.length) notes.push(t(`未解決の確認項目: ${value.report.unresolved.length}`, `Unresolved checks: ${value.report.unresolved.length}`));
    if (!value.changes.length) notes.push(t('適用できる変更はありません。', 'No applicable changes.'));
    $('proposal-warnings').textContent = notes.join('\n');
  }
  async function action(fn) {
    const s=state(); if (!valid(s) || working) return;
    const identity=++requestId; working=true;refresh();
    try {
      const result=await fn(s);
      if(identity!==requestId || state().cid!==s.cid || state().data.revision!==s.data.revision) return;
      if(result?.fingerprint) present({...result,cid:s.cid});
    } catch(error) { if(identity===requestId) {message(error.message);notice(error.message,true);} }
    finally { if(identity===requestId) {working=false;refresh();} }
  }
  async function loadConfig(cid) {
    configKey=cid;config=null;
    try { const value=await api(`${endpoint(cid)}/creative-workflow`); if(state().cid!==cid)return;config=value;refresh(); }
    catch(error) { if(state().cid===cid)message(error.message); }
  }
  function refresh() {
    const s=state();if(!s.spec)return;
    const key = `${s.cid}/${s.data.revision}/${s.job?.id || ''}/${s.output}/${s.dirty}`;
    if (key !== reviewKey) { reviewKey = key; $('kit-reviewed').checked = false; $('vision-consent').checked = false; $('kit-links').hidden = true; }
    if(s.cid!==configKey) {proposal=null;requestId++;working=false;loadConfig(s.cid);}
    if(proposal && (proposal.cid!==s.cid || proposal.base_revision!==s.data.revision)) proposal=null;
    $('proposal').hidden=!proposal;
    const enabled=valid(s)&&!working;
    $('ai-propose').disabled=!enabled || !config?.assistant.enabled || !$('ai-consent').checked;
    $('repair-layout').disabled=!enabled;
    $('inspect-quality').disabled=!enabled || !currentFilm(s);
    $('visual-review').disabled=!enabled || !currentFilm(s) || !config?.assistant.vision_enabled || !$('vision-consent').checked;
    $('build-kit').disabled=!enabled || !currentFilm(s) || !$('kit-reviewed').checked || !$('rights').checked;
    $('apply-proposal').disabled=$('apply-render-proposal').disabled=!enabled || !proposal?.changes.length || !$('proposal-reviewed').checked;
    $('apply-render-proposal').disabled ||= !$('rights').checked;
    $('workflow-fields').disabled=working;
    $('ai-provider').textContent=config?.assistant.enabled
      ? `${config.assistant.provider_host} · ${config.assistant.model} · ${t('出力上限','output limit')} ${config.assistant.max_output_tokens} tokens`
      : t('AI接続は無効です。ENABLE_CREATIVE_AI=1 と LLM_BASE_URL / LLM_MODEL の設定後に利用できます。','AI is off. Configure ENABLE_CREATIVE_AI=1, LLM_BASE_URL and LLM_MODEL to enable it.');
  }
  $('ai-propose').onclick=()=>action(async(s)=> {
    if(!$('ai-consent').checked)return;
    message(t('設定したAIに一度だけ問い合わせています。自動再送はしません。','Requesting one proposal from the configured AI. No automatic retries.'));
    const result=await api(`${endpoint(s.cid)}/creative-spec/ai-proposal`,'POST',{...refs(s),instruction:$('ai-instruction').value,external_data_consent:true});
    message(t('変更案を確認してください。まだ保存・レンダー・投稿はしていません。','Review the proposal. Nothing is saved, rendered or published.'));return result;
  });
  $('repair-layout').onclick=()=>action(async(s)=> {
    const result=await api(`${endpoint(s.cid)}/creative-spec/repair-proposal`,'POST',{...refs(s),max_passes:3});
    message(t('文字の配置・サイズを最大3回のローカル検査で調整しました。変更案を確認してください。','Checked local typography with up to three repair passes. Review the proposed changes.'));return result;
  });
  $('inspect-quality').onclick=()=>action(async(s)=> {
    const result=await api(`${endpoint(s.cid)}/creative-renders/${s.job.id}/quality/${s.output}`);
    $('quality-results').textContent=[t(`${result.sample_count}枚の実フレームを抽出。動き・音声・広告効果は未評価です。`,`${result.sample_count} actual frames sampled. Motion, audio and advertising effectiveness are not assessed.`),...result.findings.map(f=>`${f.scene_id} / ${f.output}: ${f.message}`)].join('\n');
    message(t('品質検査が完了しました。芸術的品質の点数は付けていません。','Quality inspection complete. No aesthetic score is claimed.'));
  });
  $('visual-review').onclick=()=>action(async(s)=> {
    if(!$('vision-consent').checked)return;
    message(t('最大6枚の実フレームを、設定した画像対応AIに送信しています。','Sending up to six actual frames to the configured vision model.'));
    const result=await api(`${endpoint(s.cid)}/creative-renders/${s.job.id}/visual-review`,'POST',{...refs(s),output:s.output,external_data_consent:true,frames_reviewed:true});
    message(t('映像の静止画に基づく修正案です。内容を確認してください。','Review these suggestions based on sampled still frames.'));return result;
  });
  async function apply(andRender) {
    const s=state();const p=proposal;
    if(!valid(s)||working||!p||!$('proposal-reviewed').checked)return;
    working=true;refresh();
    try {
      const result=await api(`${endpoint(s.cid)}/creative-proposals/${p.id}/apply`,'POST',{fingerprint:p.fingerprint,content_reviewed:true,...refs(s)});
      if(state().cid!==s.cid)return;
      proposal=null;await applySaved(result);
      message(t('確認した変更を保存しました。採用済み動画や既存投稿は変わりません。','Reviewed changes saved. Adopted films and existing posts are unchanged.'));
      if(andRender){working=false;await render(false);}
    }catch(error){message(error.message);notice(error.message,true);}
    finally{working=false;refresh();}
  }
  $('apply-proposal').onclick=()=>apply(false);$('apply-render-proposal').onclick=()=>apply(true);
  $('dismiss-proposal').onclick=()=>{proposal=null;refresh();};
  $('build-kit').onclick=()=>action(async(s)=> {
    if(!$('kit-reviewed').checked||!$('rights').checked)return;
    message(t('同じ制作版から動画・LP・字幕・SNS下書きをまとめています。','Packaging video, page, captions and social drafts from the same revision.'));
    const result=await api(`${endpoint(s.cid)}/creative-renders/${s.job.id}/kit`,'POST',{...refs(s),content_reviewed:true,rights_confirmed:true});
    if(state().cid!==s.cid)return;
    $('kit-download').href=result.download_url;$('kit-preview').href=result.preview_url;$('kit-links').hidden=false;
    message(t('公開パッケージを作成しました。サイト公開やSNS送信はしていません。','Launch package created. No deployment or social publication was performed。'));
  });
  for(const id of ['ai-consent','vision-consent','kit-reviewed','proposal-reviewed'])$(id).onchange=refresh;
  return {refresh};
}

// Final-film import only. Upload and review never submit an external post.
export async function mountFinalFilms(root, cid) {
  root.replaceChildren();
  const wrapper = document.createElement('div');
  root.append(wrapper);
  wrapper.innerHTML = `<form class="final-import"><div class="fields"><label>完成動画<input name="file" type="file" accept="video/mp4,video/quicktime" required></label><label>この版の名前<input name="title" maxlength="80" placeholder="紹介動画 v1" required></label></div><label class="consent"><input name="ai" type="checkbox">生成AIを使った映像・音声を含みます（自己申告）</label><label class="consent"><input name="rights" type="checkbox" required>映像・音声の利用権を確認しました。</label><p class="scope-note">取り込むとキャンペーンの公開許可を保留に戻します。すでに外部で予約・公開された投稿は取り消されません。</p><button type="submit" class="primary">完成動画を取り込む</button><progress max="100" value="0" hidden aria-label="動画アップロードの進捗"></progress><p class="final-message" role="status" aria-live="polite"></p></form><button type="button" class="final-reload">一覧を読み直す（再送信しません）</button><div class="final-library"></div>`;
  const form = wrapper.querySelector('form'), msg = wrapper.querySelector('.final-message');
  const library = wrapper.querySelector('.final-library');
  const reload = wrapper.querySelector('.final-reload');
  let films = [], selected, uploading = false, refreshing = false;
  const live = () => root.contains(wrapper);
  function message(text, error = false) { msg.textContent = text; msg.classList.toggle('error', error); }
  function renderLibrary() {
    if (!live()) return;
    library.replaceChildren();
    if (!films.length) { const p=document.createElement('p');p.className='scope-note';p.textContent='完成動画はまだありません。生成映像・AE演出・実録画を仕上げたMP4を取り込んでください。';library.append(p);return; }
    const film = films.find(f=>f.id===selected)||films[0];selected=film.id;
    const section=document.createElement('section');section.className='final-review';
    const video=document.createElement('video');video.controls=true;video.playsInline=true;video.preload='metadata';video.src=film.url;video.setAttribute('aria-label','取り込んだ完成動画');
    const detail=document.createElement('div'), heading=document.createElement('h3'), info=document.createElement('p'), note=document.createElement('p'), hash=document.createElement('p'), link=document.createElement('a');
    heading.textContent=film.title;
    info.textContent=`${film.width} × ${film.height} · ${film.duration.toFixed(1)}秒 · ${(film.bytes/1024/1024).toFixed(1)} MB`;
    note.textContent=film.ai_generated?'生成AIを含むと申告されています。公開前に表示・権利を確認してください。':'生成AIを含まないと申告されています。これはAI検出の判定ではありません。';
    hash.className='final-hash';hash.textContent='SHA-256 '+film.sha256;
    link.textContent='この動画で投稿内容を確認 ↗';link.href='/?'+new URLSearchParams({campaign:cid,tab:'distribution',media:film.media});
    detail.append(heading,info,note,hash,link);section.append(video,detail);library.append(section);
    if(films.length>1){const history=document.createElement('details');history.className='final-history';const title=document.createElement('summary');title.textContent=`保存した版を見る（${films.length}件）`;history.append(title);for(const f of films){const b=document.createElement('button');b.type='button';b.textContent=f.title;b.disabled=f.id===selected;b.onclick=()=>{selected=f.id;renderLibrary();};history.append(b);}library.append(history);}
  }
  async function refresh() {
    const response=await fetch(`/api/campaigns/${encodeURIComponent(cid)}/final-films`,{credentials:'same-origin'});
    if(!response.ok)throw new Error('完成動画の一覧を読み込めませんでした。スタジオへのログイン状態を確認してください。');
    const data=await response.json();
    if(!Array.isArray(data.items))throw new Error('一覧の形式を確認できませんでした。入力は変更していません。');
    films=data.items;renderLibrary();
  }
  reload.addEventListener('click', async () => {
    if(uploading || refreshing || !live())return;
    refreshing=true;reload.disabled=true;
    form.querySelector('button[type="submit"]').disabled=true;
    try { await refresh(); message('一覧を更新しました。取り込んだ動画があるか確認してください。動画は再送信していません。'); }
    catch(error) { message(error.message,true); }
    finally { refreshing=false;reload.disabled=false;form.querySelector('button[type="submit"]').disabled=uploading; }
  });
  const unload = e => {if(uploading){e.preventDefault();e.returnValue='';}};
  form.addEventListener('submit', async event => {
    event.preventDefault();if(uploading||refreshing||!form.reportValidity())return;
    const file=form.elements.file.files[0];
    if(!file||!file.size||file.size>200*1024*1024){message('0バイトより大きく、200 MB以下のMP4を選択してください。',true);return;}
    uploading=true;reload.disabled=true;window.addEventListener('beforeunload',unload);form.querySelector('button').disabled=true;
    const progress=form.querySelector('progress');progress.hidden=false;progress.value=0;
    message('動画をアップロードしています。外部サービスには送信しません。');
    try {
      const film=await new Promise((resolve,reject)=>{
        const x=new XMLHttpRequest();
        const query=new URLSearchParams({title:form.elements.title.value.trim(),ai_generated:String(form.elements.ai.checked),rights_confirmed:'true'});
        x.open('POST',`/api/campaigns/${encodeURIComponent(cid)}/final-films/media?${query}`);x.withCredentials=true;x.timeout=240000;x.setRequestHeader('Content-Type','application/octet-stream');
        x.upload.onprogress=e=>{if(e.lengthComputable)progress.value=e.loaded/e.total*100;};
        x.upload.onload=()=>{progress.removeAttribute('value');message('アップロード済み。映像・音声を検査しています。');};
        x.onload=()=>{let data;try{data=JSON.parse(x.responseText);}catch{reject(new Error('取り込み結果を読み取れませんでした。一覧を再読み込みして確認してください。'));return;}if(x.status>=200&&x.status<300)resolve(data);else reject(new Error(typeof data.detail==='string'?data.detail:'入力内容を確認してください。'));};
        x.onerror=()=>reject(new Error('通信が切れました。再実行の前に一覧を再読み込みして、取り込み結果を確認してください。'));
        x.ontimeout=()=>reject(new Error('処理結果が不明です。再アップロードせず、一覧を再読み込みして確認してください。'));
        x.send(file);
      });
      if(!film || typeof film.id!=='string' || !film.id)throw new Error('受付結果を確認できませんでした。再アップロードせず、一覧を読み直してください。');
      selected=film.id;
      // The upload already succeeded. A subsequent GET failure must not look like
      // an upload failure or encourage submitting the same film again.
      form.reset();
      try { await refresh(); message('完成動画を保存しました。映像を確認してから投稿準備へ進んでください。まだ公開していません。'); }
      catch { message('動画の保存は完了しましたが、一覧を更新できませんでした。「一覧を読み直す」で確認してください。再アップロードは不要です。',true); }
    }catch(error){message(error.message,true);}
    finally{uploading=false;reload.disabled=false;window.removeEventListener('beforeunload',unload);form.querySelector('button').disabled=false;progress.hidden=true;}
  });
  try{await refresh();}catch(error){message(error.message,true);}
}

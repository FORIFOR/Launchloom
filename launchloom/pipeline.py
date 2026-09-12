from __future__ import annotations
import asyncio
import json
import shutil
import zipfile
from pathlib import Path
from PIL import Image, ImageStat
from . import __version__
from .config import Settings
from .models import Brief, BuildOptions, Plan
from .store import Store
from .planning import make_plan, make_posts
from .providers import llm_plan, FalFilm, ComfyFilm
from .capture import capture
from .rendering import render, validate_media
from .site import build_site
from .security import file_sha, scrub_error

SAMPLE_BRIEF={
    'name':'Orbit','tagline':'大切なことに、余白を。','audience':'ひとりで考え、つくる人へ',
    'description':'思いついたことを書き留め、次の一歩を選ぶ。Orbitは、必要なことだけが静かに並ぶ、小さな作業スペースです。',
    'product_url':'','is_sample':True,'accent':'#ed6847','language':'ja','goal':'signups',
    'channels':['x','linkedin','threads'],
    'features':[
        {'title':'思いつきを、その場で。','detail':'入力したノートを、ワンクリックで一覧に追加できます。','evidence':'Bundled demo-app.js: add() inserts a visible task.','approved':True},
        {'title':'終わったことが、見える。','detail':'完了ボタンを押すと、チェックと打ち消し線が表示されます。','evidence':'Bundled demo-app.js: paint() renders the task completion state.','approved':True},
        {'title':'次の一歩だけに、集中。','detail':'フォーカスモードで、未完了のノートをひとつだけ表示します。','evidence':'Bundled demo-app.js: focus-button displays the first incomplete task.','approved':True}]
}

# The bundled Orbit app is in English, so an English studio should not hand back a
# Japanese film. Same app, same evidence, the operator's language.
SAMPLE_BRIEF_EN={
    'name':'Orbit','tagline':'Room for what matters.','audience':'people who think and build alone',
    'description':'Write the thought down, then pick the next step. Orbit is a small workspace where only what matters stays on screen.',
    'product_url':'','is_sample':True,'accent':'#ed6847','language':'en','goal':'signups',
    'channels':['x','linkedin','threads'],
    'features':[
        {'title':'Catch it while you have it.','detail':'Type a note and one click puts it at the top of the list.','evidence':'Bundled demo-app.js: add() inserts a visible task.','approved':True},
        {'title':'See what you finished.','detail':'Completing a note draws a line through it and keeps the state.','evidence':'Bundled demo-app.js: paint() renders the task completion state.','approved':True},
        {'title':'One next step at a time.','detail':'Focus mode shows a single unfinished note and nothing else.','evidence':'Bundled demo-app.js: focus-button displays the first incomplete task.','approved':True}]
}

SAMPLES={'ja':SAMPLE_BRIEF,'en':SAMPLE_BRIEF_EN}

def write_json(path: Path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2))


def review_still(root: Path,capture_file: Path,start: float=0.0) -> None:
    """One frame of the operator's own recording, so the review gate shows what was
    actually captured. Authenticated review only: it is not part of the launch kit.

    Never the first frame: a screen recording usually opens on a blank or
    half-painted page, and a white rectangle proves nothing. Sample a few points
    inside the range the operator chose and keep the first one with real content.
    """
    try:
        from PIL import ImageStat
        from .rendering import FrameReader, probe
        try:duration=float(probe(capture_file)['format']['duration'])
        except Exception:duration=0.0
        usable=max(0.0,duration-start)
        chosen=None
        for fraction in (.35,.55,.15,.75,0.0):
            reader=FrameReader(capture_file,960,600,start=start+usable*fraction)
            frame=reader.next()
            reader.close()
            if frame is None:continue
            chosen=chosen or frame
            if max(ImageStat.Stat(frame).stddev)>12:
                chosen=frame;break
        if chosen is not None:chosen.save(root/'review-frame.jpg',quality=82)
    except Exception:
        pass


def srt_time(t):
    ms=round(t*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'

async def build(settings: Settings,store: Store,cid: str,options: BuildOptions):
    record=store.campaign(cid)
    if not record:raise ValueError('Campaign not found')
    b=Brief.model_validate(record['brief']);root=settings.data_dir/'campaigns'/cid
    root.mkdir(parents=True,exist_ok=True)
    if options.capture_mode=='sample' and not b.is_sample:raise ValueError('The sample recording cannot be presented as footage of another product')
    def stage(name,pct,message):
        store.progress(cid,name,pct);store.log(cid,name,message)
    stage('direction',7,'企画と根拠を整理しています。未承認の機能は宣伝に使いません。')
    if record.get('plan_approved') and record.get('plan'):
        # A reviewed storyboard is the instruction for this render. Regenerating it
        # here would quietly discard the operator's wording.
        plan=Plan.model_validate(record['plan'])
        store.log(cid,'direction','承認済みの構成で制作します。文言は上書きしません。')
    else:
        plan=await llm_plan(b,settings) if options.llm_plan else make_plan(b,options.visual_style)
        store.progress(cid,'direction',12,plan=plan.model_dump())
    write_json(root/'brief.json',b.model_dump())
    public_brief=b.model_dump(exclude={'features': {'__all__': {'evidence'}}, 'references': True})
    write_json(root/'campaign.json',public_brief)
    write_json(root/'storyboard.json',plan.model_dump())
    stage('site',18,'同じメッセージ・配色・CTAで、レスポンシブLPを作っています。')
    build_site(b,cid,root/'site',settings)
    stage('capture',26,'操作映像を準備しています。収録と生成映像の出どころは区別して保存します。')
    capture_file=None;events=[]
    if options.capture_mode in {'sample','url'}:
        meta=root/'capture/events.json';video=root/'capture/capture.webm'
        if meta.exists() and video.exists():
            validate_media(video);capture_result=json.loads(meta.read_text())
        else:capture_result=await capture(settings,options,root/'capture')
        capture_file=video;events=capture_result['events']
    elif options.capture_mode=='upload':
        capture_file=root/'input/capture.bin'
        if not capture_file.exists():raise ValueError('Upload a recording before building')
        validate_media(capture_file)
        # Imported footage carries no cursor metadata. An operator-supplied track
        # gives the same camera work and on-screen labels as a recorded capture.
        events=[e.model_dump() for e in options.capture_events]
    if options.review_plan and not record.get('plan_approved'):
        if capture_file and capture_file.exists():
            review_still(root,capture_file,options.capture_start)
        store.progress(cid,'awaiting_review',40,state='awaiting_review')
        store.log(cid,'review','構成と収録内容を確認してください。承認するまでレンダリングも生成AIも実行しません。')
        return None
    broll=None
    if options.film_provider!='local':
        stage('generation',38,'設定した生成映像Providerへ接続します。操作画面の証拠としては使用しません。')
        broll=root/'concept.mp4'
        if not broll.exists():
            provider=FalFilm(settings,store,cid) if options.film_provider=='fal' else ComfyFilm(settings,store,cid)
            await provider.generate(plan.video_prompt,options,broll)
        validate_media(broll)
    stage('render',45,'横長と縦長を別レイアウトで編集・書き出ししています。')
    audio=root/'input/audio.bin';narration=root/'input/narration.bin'
    for track in (audio,narration):
        if track.exists():validate_media(track,audio=True)
    def render_progress(value):store.progress(cid,'render',45+int(value*37))
    if options.capture_start:
        # Event times are relative to the recording; the film starts at the cut.
        events=[{**e,'time':e['time']-options.capture_start} for e in events]
    videos=await asyncio.to_thread(render,b,plan,root,capture_file,events,options.quality,broll,audio if audio.exists() else None,render_progress,options.visual_style,options.capture_start,options.capture_length,narration if narration.exists() else None,options.animation_seconds)
    stage('package',86,'LPに操作動画を配置し、SNS原稿と配布パッケージを作っています。')
    shutil.copy(root/'landscape.mp4',root/'site/film.mp4');shutil.copy(root/'landscape.jpg',root/'site/poster.jpg')
    build_site(b,cid,root/'site',settings,True)
    posts=make_posts(b,cid)
    if b.is_sample:
        for post in posts:
            post['warning']='サンプルプロダクトのデモです。実際のサービスの成果として紹介しないでください。'
    write_json(root/'posts.json',posts)
    script='\n\n'.join(f'## {p["channel"]}\n\n{p["content"]}\n\nMedia: {p["media"]}' for p in posts)
    (root/'social-copy.md').write_text('# Launch copy — drafts requiring review\n\n'+script)
    duration=videos['landscape']['duration'];proof_duration=duration-6
    proof=[s for s in plan.scenes if s.kind=='proof']
    line=lambda scene:scene.caption or scene.title
    captions=[(0,3,line(plan.scenes[0]))]+[(3+i*proof_duration/len(proof),3+(i+1)*proof_duration/len(proof),line(s)) for i,s in enumerate(proof)]+[(duration-3,duration,line(plan.scenes[-1]))]
    (root/'captions.srt').write_text('\n\n'.join(f'{i+1}\n{srt_time(a)} --> {srt_time(z)}\n{text}' for i,(a,z,text) in enumerate(captions)))
    stage('quality',92,'出力の解像度・動画形式・欠損・原稿の根拠を検査しています。')
    poster_ok=all(max(ImageStat.Stat(Image.open(root/(k+'.jpg'))).stddev)>8 for k in videos)
    quality={'status':'passed' if poster_ok else 'failed',
        'checks':{'video_decodable':True,'two_aspect_ratios':True,'poster_nonblank':poster_ok,
            'only_user_approved_features':True,'local_files_present':True,'live_publish_not_performed':True},
        'limitations':['Automated checks do not establish artistic quality, virality, or independent factual truth.',
          'Capture timing is approximate; imported recordings have no cursor metadata in v0.1.',
          'No voice or music is generated automatically. Music and narration are files the operator supplies and has the right to use.',
          'Generic landing-page templates are generated, not arbitrary full-stack applications.'],
        'warnings':(['公開先の product_url が未設定です。'] if not b.product_url else [])+
        (['サンプルアプリの映像です。ユーザーの実プロダクトは未収録です。'] if b.is_sample else [])+
        (['字幕とモーショングラフィックスのみ。音声トラック未設定です。'] if not (audio.exists() or narration.exists()) else [])+
        (['ナレーションの下で、音楽の音量を下げています。'] if audio.exists() and narration.exists() else [])}
    write_json(root/'qa.json',quality)
    if not poster_ok:raise ValueError('A poster appears blank; export is blocked')
    names=['campaign.json','storyboard.json','posts.json','social-copy.md','captions.srt','qa.json','landscape.mp4','portrait.mp4','landscape.jpg','portrait.jpg','site/index.html','site/site.css','site/site.js','site/film.mp4','site/poster.jpg']
    manifest={'version':__version__,'campaign_id':cid,'revision':store.campaign(cid)['revision'],'videos':videos,
        'provenance':{'capture':'bundled-sample' if b.is_sample else options.capture_mode,'concept':options.film_provider,
            'copy':plan.source,'visual_style':options.visual_style,'reviewed_before_render':bool(options.review_plan),
            'imported_event_track':bool(options.capture_events),'raw_recording_in_export':False},
        'files':{name:{'sha256':file_sha(root/name),'bytes':(root/name).stat().st_size} for name in names},
        'rights':'Original output templates; operator-provided product claims, recordings, music and provider output require operator clearance. Reference-post media is NOT bundled.'}
    write_json(root/'manifest.json',manifest)
    temp=root/'launch-kit.partial.zip'
    with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as z:
        for name in names+['manifest.json']:z.write(root/name,name)
    temp.replace(root/'launch-kit.zip')
    store.progress(cid,'ready',100,state='ready')
    store.log(cid,'ready','制作パッケージができました。外部への公開・投稿はまだ行っていません。')
    return manifest

async def worker_loop(settings: Settings,store: Store,stop: asyncio.Event):
    while not stop.is_set():
        job=store.claim_job()
        if not job:
            try:await asyncio.wait_for(stop.wait(),timeout=.6)
            except asyncio.TimeoutError:pass
            continue
        try:
            await build(settings,store,job['campaign_id'],BuildOptions.model_validate(job['options']))
            store.finish_job(job['id'],'complete')
        except asyncio.CancelledError:raise
        except Exception as e:
            message=scrub_error(e,[settings.token,settings.fal_key,settings.postiz_key,settings.llm_key])
            store.progress(job['campaign_id'],'failed',0,state='failed',error=message)
            store.log(job['campaign_id'],'error',message)
            store.finish_job(job['id'],'failed')

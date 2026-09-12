from __future__ import annotations
import functools
import json
import math
import os
import shutil
import subprocess
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
from .models import Brief, Plan

FPS=24

# Fonts that cover Japanese. A Latin-only fallback renders CJK as tofu boxes,
# so the resolved file is reported by `launchloom doctor` before a build starts.
CJK_FONTS={True:['/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
                 '/usr/share/fonts/opentype/noto/NotoSansJP-Bold.otf',
                 '/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc',
                 '/Library/Fonts/ヒラギノ角ゴシック W6.ttc',
                 'C:/Windows/Fonts/YuGothB.ttc','C:/Windows/Fonts/meiryob.ttc'],
           False:['/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
                  '/usr/share/fonts/opentype/noto/NotoSansJP-Regular.otf',
                  '/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc',
                  '/Library/Fonts/ヒラギノ角ゴシック W3.ttc',
                  'C:/Windows/Fonts/YuGothR.ttc','C:/Windows/Fonts/meiryo.ttc']}
LATIN_FONTS={True:['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf','/System/Library/Fonts/Helvetica.ttc','C:/Windows/Fonts/arialbd.ttf'],
             False:['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf','/System/Library/Fonts/Helvetica.ttc','C:/Windows/Fonts/arial.ttf']}


def font_source(bold: bool = False) -> tuple[str,bool]:
    """Return the font file used for rendering and whether it covers Japanese."""
    chosen=os.getenv('LAUNCHLOOM_FONT_BOLD' if bold else 'LAUNCHLOOM_FONT','')
    if chosen and Path(chosen).exists():return chosen,True
    for candidate in CJK_FONTS[bold]:
        if Path(candidate).exists():return candidate,True
    for candidate in LATIN_FONTS[bold]:
        if Path(candidate).exists():return candidate,False
    return '',False


@functools.lru_cache(maxsize=64)
def font(size: int, bold: bool = False):
    path,_=font_source(bold)
    if path:
        try:return ImageFont.truetype(path,size)
        except OSError:pass
    return ImageFont.load_default(size=size)


def run(args: list[str],timeout=120):
    proc=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
    if proc.returncode:raise RuntimeError(f'{Path(args[0]).name} failed: '+proc.stderr.decode(errors='replace')[-1200:])
    return proc.stdout


def probe(path: Path) -> dict:
    try:
        result=json.loads(run(['ffprobe','-v','error','-protocol_whitelist','file,pipe','-show_format','-show_streams','-of','json',str(path)],30))
    except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        raise ValueError('Media cannot be decoded or probed safely. Supply a valid MP4, WebM or audio file.') from e
    duration=float(result.get('format',{}).get('duration',0))
    if not 0<duration<=300:raise ValueError('Media duration must be between 0 and 300 seconds')
    return result


def validate_media(path: Path,audio=False):
    result=probe(path)
    kind='audio' if audio else 'video'
    streams=[s for s in result['streams'] if s.get('codec_type')==kind]
    if not streams:raise ValueError('The uploaded file has no '+kind+' stream')
    if not audio and (streams[0].get('width',0)>4096 or streams[0].get('height',0)>4096):
        raise ValueError('Input media is limited to 4096 pixels per dimension')
    return result


class FrameReader:
    def __init__(self,path: Path,width=1280,height=800,start=0.0):
        self.width=width;self.height=height;self.last=None
        # -ss before -i seeks by keyframe index instead of decoding the skipped part.
        seek=['-ss',f'{start:.3f}'] if start>0 else []
        self.proc=subprocess.Popen(['ffmpeg','-v','error','-nostdin','-protocol_whitelist','file,pipe',*seek,'-i',str(path),
            '-vf',f'fps={FPS},scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2',
            '-an','-threads','2','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    def next(self):
        size=self.width*self.height*3;data=self.proc.stdout.read(size)
        if len(data)==size:self.last=Image.frombytes('RGB',(self.width,self.height),data)
        return self.last
    def close(self):
        self.proc.stdout.close()
        if self.proc.poll() is None:self.proc.terminate()
        try:self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait()


def smooth(x):
    x=max(0,min(1,x));return x*x*(3-2*x)

def smoother(x):
    """C2-continuous easing for camera motion: no velocity/acceleration snap at cuts."""
    x=max(0,min(1,x));return x*x*x*(x*(x*6-15)+10)


def wrapped(draw,text,xy,width,size,fill,bold=False,max_lines=4):
    f=font(size,bold);lines=[];line=''
    # Character-safe wrapping works for Japanese and Latin without clipping.
    for ch in str(text):
        if ch=='\n' or (line and draw.textlength(line+ch,font=f)>width):
            lines.append(line);line='' if ch=='\n' else ch
        else:line+=ch
    if line:lines.append(line)
    if len(lines)>max_lines:
        lines=lines[:max_lines];lines[-1]=lines[-1][:-1]+'…'
    x,y=xy
    for line in lines:draw.text((x,y),line,font=f,fill=fill);y+=int(size*1.42)
    return y


def _camera_keyframes(events: list[dict]):
    """Turn interaction events into restrained, Screen Studio-like camera shots.

    The important behavior is that a click creates a *held shot*, not a zoom pulse.
    We only move again when a later interaction is far enough away to deserve a new shot.
    """
    frames=[{'time':0.0,'x':0.5,'y':0.5,'zoom':1.02}]
    for event in events:
        action=event.get('action','click')
        if action not in {'click','fill','scroll'}:
            continue
        x=float(event.get('x',0.5));y=float(event.get('y',0.5))
        # Screen recordings look calmer when the focus is biased away from extreme edges.
        x=max(.20,min(.80,x));y=max(.22,min(.78,y))
        zoom=1.17 if action=='click' else 1.13 if action=='fill' else 1.06
        previous=frames[-1]
        distance=math.hypot(x-previous['x'],y-previous['y'])
        # Ignore tiny target changes. They read as camera jitter, not useful direction.
        if distance < .075 and abs(zoom-previous['zoom']) < .045:
            continue
        frames.append({'time':max(0.0,float(event.get('time',0.0))-.18),'x':x,'y':y,'zoom':zoom})
    return frames

def camera_pose(t: float,events: list[dict]):
    frames=_camera_keyframes(events)
    current=frames[0];previous=frames[0]
    for frame in frames[1:]:
        if frame['time']<=t:
            previous=current;current=frame
        else:
            break
    if current is frames[0]:
        return current['x'],current['y'],current['zoom']
    # Long enough to feel deliberate, short enough to keep up with UI demos.
    transition=.82
    phase=smoother((t-current['time'])/transition)
    x=previous['x']+(current['x']-previous['x'])*phase
    y=previous['y']+(current['y']-previous['y'])*phase
    zoom=previous['zoom']+(current['zoom']-previous['zoom'])*phase
    return x,y,zoom

def crop_camera(frame: Image.Image,size: tuple[int,int],t: float,events: list[dict]):
    tw,th=size;w,h=frame.size
    x,y,zoom=camera_pose(t,events)
    ratio=tw/th
    # First fit the requested aspect ratio, then apply the virtual camera zoom.
    if w/h>=ratio:
        base_h=h;base_w=h*ratio
    else:
        base_w=w;base_h=w/ratio
    cw=base_w/zoom;ch=base_h/zoom
    # Clamp to screen; a focus point never exposes an empty edge.
    cx=max(cw/2,min(w-cw/2,x*w));cy=max(ch/2,min(h-ch/2,y*h))
    box=(round(cx-cw/2),round(cy-ch/2),round(cx+cw/2),round(cy+ch/2))
    return frame.crop(box).resize(size,Image.Resampling.LANCZOS)


# Three original visual directions. They change ground, ink and structure, so a
# second take reads as a different film rather than the same film recoloured.
STYLES={
  'editorial':{'ground':(241,239,233),'light':(5,-3,-8),'ink':'#182324','muted':'#687575','rule':'#d8d7cf',
    'panel':'#182324','panel_ink':'#f5f0e5','panel_muted':'#a0b1a9','outro':'#182324','outro_ink':'#f9f4e9',
    'outro_muted':'#a2b4ab','outro_rule':'#344848','fade':'#f1efe9','glow':True,'grid':False,
    'direction':'Quiet typography, a warm accent, restrained motion, readable real-product footage.'},
  'spotlight':{'ground':(22,26,28),'light':(16,14,10),'ink':'#f7f2e7','muted':'#95a59e','rule':'#31403f',
    'panel':'#0d1314','panel_ink':'#f5f0e5','panel_muted':'#8fa39b','outro':'#0d1314','outro_ink':'#f9f4e9',
    'outro_muted':'#93a39c','outro_rule':'#2b3a3a','fade':'#101617','glow':True,'grid':False,
    'direction':'A dark room and one pool of light. The product is the only lit surface; type stays small and certain.'},
  'grid':{'ground':(236,238,235),'light':(3,-2,-5),'ink':'#141f1e','muted':'#69786f','rule':'#ccd3cc',
    'panel':'#1b2626','panel_ink':'#f2efe6','panel_muted':'#9fb0a8','outro':'#1b2626','outro_ink':'#f7f3e9',
    'outro_muted':'#9fb0a8','outro_rule':'#344444','fade':'#eceeea','glow':False,'grid':True,
    'direction':'A measured grid, small capitals and hard edges. Structure carries the message; nothing floats.'}}


@functools.lru_cache(maxsize=12)
def background(w,h,visual_style='editorial'):
    style=STYLES.get(visual_style,STYLES['editorial'])
    yy,xx=np.mgrid[0:h,0:w]
    light=np.exp(-(((xx-w*.82)/(w*.5))**2+((yy-h*.2)/(h*.6))**2)) if style['glow'] else np.zeros((h,w))
    base=np.empty((h,w,3),dtype=np.uint8)
    for c,value in enumerate(style['ground']):
        base[:,:,c]=np.clip(value+light*style['light'][c],0,255)
    image=Image.fromarray(base)
    if style['grid']:
        d=ImageDraw.Draw(image);step=max(24,round(w/32))
        for x in range(0,w,step):d.line((x,0,x,h),fill=style['rule'],width=1)
        for y in range(0,h,step):d.line((0,y,w,y),fill=style['rule'],width=1)
    return image


def rounded_paste(base,content,x,y,radius=20):
    mask=Image.new('L',content.size,0);ImageDraw.Draw(mask).rounded_rectangle((0,0,content.width-1,content.height-1),radius,fill=255)
    shadow=Image.new('RGBA',base.size,(0,0,0,0));sd=ImageDraw.Draw(shadow)
    sd.rounded_rectangle((x,y+12,x+content.width,y+content.height+12),radius,fill=(20,30,25,42))
    base.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(16)))
    base.paste(content,(x,y),mask)


def render_frame(brief,plan,w,h,t,proof_duration,raw,events,broll=None,visual_style='editorial'):
    portrait=h>w;s=w/720 if portrait else w/1280
    def n(v):return max(1,round(v*s))
    style=STYLES.get(visual_style,STYLES['editorial'])
    accent=brief.accent;dark=style['ink'];muted=style['muted']
    base=background(w,h,visual_style).convert('RGBA');d=ImageDraw.Draw(base)
    margin=n(48 if portrait else 54)
    d.rounded_rectangle((margin,margin,margin+n(25),margin+n(25)),n(7),fill=accent)
    d.text((margin+n(38),margin-n(2)),brief.name,font=font(n(19),True),fill=dark)
    d.text((w-margin-n(112),margin),'PRODUCT FILM',font=font(n(11)),fill=muted)
    intro=3;outro_start=intro+proof_duration;duration=outro_start+3
    if t<intro:
        if broll is not None:
            image=ImageOps.fit(broll,(w,h),method=Image.Resampling.LANCZOS)
            base=Image.blend(image.convert('RGBA'),Image.new('RGBA',(w,h),'#121b1c'),.48)
            d=ImageDraw.Draw(base);dark='#ffffff';muted='#d1d8d4'
            d.text((margin,margin),'AI-GENERATED CONCEPT',font=font(n(12)),fill=muted)
        else:
            cx=w*.80 if not portrait else w*.66;cy=h*.47 if not portrait else h*.58
            shift=math.sin(t*.6)*n(14)
            for i in range(9):
                r=n(90+i*25)+shift
                d.ellipse((cx-r,cy-r*.86,cx+r,cy+r*.86),outline=accent if i==4 else style['rule'],width=n(3 if i==4 else 1))
            d.ellipse((cx-n(13),cy-n(13),cx+n(13),cy+n(13)),fill=accent)
        offset=n(25)*(1-smooth(t/.7))
        d.text((margin,n(183 if portrait else 196)+offset),'GOOD WORK DESERVES TO BE SEEN.',font=font(n(11)),fill=muted)
        yy=wrapped(d,brief.tagline,(margin,n(237 if portrait else 238)+offset),n(595 if portrait else 770),n(60 if portrait else 57),dark,True,4)
        wrapped(d,brief.audience,(margin,yy+n(22)),n(560 if portrait else 570),n(18),muted,max_lines=2)
        d.text((margin,h-n(98)),'01  /  A DIFFERENT WAY FORWARD',font=font(n(12)),fill=muted)
    elif t<outro_start:
        tt=t-intro
        proofs=[sc for sc in plan.scenes if sc.kind=='proof']
        sc=proofs[min(len(proofs)-1,int(tt/max(.001,proof_duration)*len(proofs)))]
        label=next((e['label'] for e in reversed(events) if e['time']<=tt and e.get('label')),sc.title)
        if portrait:
            d.text((margin,n(137)),('REAL PRODUCT / SAMPLE APP' if brief.is_sample else 'REAL PRODUCT' if raw is not None else 'FEATURE OVERVIEW'),font=font(n(12)),fill=muted)
            wrapped(d,sc.title,(margin,n(178)),w-margin*2,n(48),dark,True,3)
            cw=w-margin*2;ch=n(568);x=margin;y=n(398)
        else:
            d.text((margin,n(154)),f'0{proofs.index(sc)+1} / IN PRACTICE',font=font(n(12)),fill=muted)
            yy=wrapped(d,sc.title,(margin,n(205)),n(233),n(31),dark,True,4)
            wrapped(d,sc.detail,(margin,yy+n(22)),n(233),n(16),muted,max_lines=5)
            x=n(342);y=n(118);cw=n(882);ch=n(550)
        if raw is not None:
            image=crop_camera(raw,(cw,ch),tt,events)
            rounded_paste(base,image,x,y,n(18))
            d=ImageDraw.Draw(base)
        else:
            d.rounded_rectangle((x,y,x+cw,y+ch),n(20),fill=style['panel'])
            wrapped(d,sc.title,(x+n(44),y+ch//3),cw-n(88),n(40),style['panel_ink'],True)
            d.text((x+n(44),y+ch-n(60)),'FEATURE OVERVIEW · NOT A SCREEN RECORDING',font=font(n(10)),fill=style['panel_muted'])
        if portrait:
            wrapped(d,label,(margin,n(1015)),w-margin*2,n(25),dark,True,2)
            wrapped(d,sc.detail,(margin,n(1100)),w-margin*2,n(17),muted,max_lines=2)
    else:
        d.rectangle((0,0,w,h),fill=style['outro'])
        cx=w*.83;cy=h*.81;r=n(210+25*math.sin((t-outro_start)*.5))
        for i in range(5):
            rr=r+i*n(22)
            d.ellipse((cx-rr,cy-rr,cx+rr,cy+rr),outline=style['outro_rule'],width=n(1))
        d.rounded_rectangle((margin,margin,margin+n(25),margin+n(25)),n(7),fill=accent)
        d.text((margin+n(40),margin-n(2)),brief.name,font=font(n(19),True),fill=style['outro_ink'])
        d.text((margin,n(244 if portrait else 201)),'LESS EXPLAINING. MORE EXPERIENCING.',font=font(n(11)),fill=style['outro_muted'])
        yy=wrapped(d,plan.scenes[-1].title,(margin,n(297 if portrait else 254)),w-margin*2,n(58 if portrait else 56),style['outro_ink'],True,4)
        py=min(h-n(195),yy+n(56));buttonw=min(w-margin*2,n(280));buttonh=n(59)
        d.rounded_rectangle((margin,py,margin+buttonw,py+buttonh),n(29),fill=accent)
        d.text((margin+n(24),py+n(12)),plan.scenes[-1].detail+'  ↗',font=font(n(19),True),fill='#142122')
        if brief.is_sample:d.text((margin,h-n(82)),'SAMPLE PRODUCT · LOCAL DEMO',font=font(n(11)),fill=style['outro_muted'])
    # Stable frame-specific animation and a legible timeline; no wall-clock dependency.
    d=ImageDraw.Draw(base)
    d.rectangle((0,h-n(4),round(w*t/duration),h),fill=accent)
    if t<.28:base=Image.blend(Image.new('RGBA',(w,h),style['fade']),base,smooth(t/.28))
    return base.convert('RGB')


def render(brief: Brief,plan: Plan,output: Path,capture_path: Path | None,events: list[dict],quality='hd',broll: Path|None=None,audio: Path|None=None,progress=None,visual_style='editorial',capture_start=0.0,capture_length=0.0):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):raise ValueError('Install FFmpeg and ffprobe before rendering')
    output.mkdir(parents=True,exist_ok=True)
    actual_duration=float(validate_media(capture_path)['format']['duration']) if capture_path else 9
    available=actual_duration-capture_start if capture_path else actual_duration
    if capture_path and available<1:
        raise ValueError('The chosen range starts at or past the end of the recording')
    proof_duration=min(capture_length or 20,available);duration=proof_duration+6
    result={}
    for i,(name,w,h) in enumerate([('landscape',1280,720),('portrait',720,1280)]):
        if quality=='draft':w=int(w*.75);h=int(h*.75)
        rawreader=FrameReader(capture_path,start=capture_start) if capture_path else None
        brollreader=FrameReader(broll) if broll else None
        target=output/(name+'.mp4');temp=output/(name+'.rendering.mp4')
        log=(output/(name+'.render.log')).open('wb')
        encoder=subprocess.Popen(['ffmpeg','-v','error','-y','-nostdin','-f','rawvideo','-pix_fmt','rgb24','-s',f'{w}x{h}','-r',str(FPS),'-i','pipe:0',
            '-an','-c:v','libx264','-preset','veryfast','-crf','21','-pix_fmt','yuv420p','-movflags','+faststart','-threads','2',str(temp)],stdin=subprocess.PIPE,stderr=log)
        success=False
        try:
            count=math.ceil(duration*FPS)
            for k in range(count):
                t=k/FPS
                raw=rawreader.next() if rawreader and 3<=t<3+proof_duration else None
                bframe=brollreader.next() if brollreader and t<3 else None
                image=render_frame(brief,plan,w,h,t,proof_duration,raw,events,bframe,visual_style)
                if k==int(4.5*FPS):image.save(output/(name+'.jpg'),quality=90)
                encoder.stdin.write(image.tobytes())
                if progress and k%48==0:progress(i/2+k/count/2)
            encoder.stdin.close()
            if encoder.wait(timeout=90):raise RuntimeError('Video encoder failed; inspect the render log')
            if audio:
                run(['ffmpeg','-v','error','-y','-nostdin','-protocol_whitelist','file,pipe','-i',str(temp),'-i',str(audio),'-map','0:v:0','-map','1:a:0',
                    '-c:v','copy','-af','apad,loudnorm=I=-16:TP=-1.5:LRA=11','-c:a','aac','-b:a','160k','-t',str(duration),'-movflags','+faststart',str(target)])
                temp.unlink(missing_ok=True)
            else:temp.replace(target)
            metadata=probe(target);video=next(s for s in metadata['streams'] if s['codec_type']=='video')
            if video['width']!=w or video['height']!=h or video['codec_name']!='h264':raise ValueError('Video quality gate failed')
            result[name]={'file':target.name,'width':w,'height':h,'duration':float(metadata['format']['duration']),'fps':FPS,'codec':'h264','bytes':target.stat().st_size,'audio':bool(audio)}
            success=True
        finally:
            if encoder.poll() is None:encoder.kill();encoder.wait()
            log.close()
            if rawreader:rawreader.close()
            if brollreader:brollreader.close()
            if not success:temp.unlink(missing_ok=True)
    return result


def normalize_upload(path: Path,audio: bool=False) -> None:
    """Browser MediaRecorder WebM often has no duration header. Remux locally,
    never re-encode, into a bounded seekable file before final validation."""
    try:
        validate_media(path,audio)
        return
    except ValueError:
        pass
    try:
        raw=json.loads(run(['ffprobe','-v','error','-protocol_whitelist','file,pipe',
            '-show_format','-show_streams','-of','json',str(path)],30))
    except (RuntimeError,subprocess.TimeoutExpired,json.JSONDecodeError) as e:
        raise ValueError('Media cannot be decoded safely') from e
    streams=[s for s in raw.get('streams',[]) if s.get('codec_type')==('audio' if audio else 'video')]
    if not streams:raise ValueError('The file has no requested media stream')
    duration=raw.get('format',{}).get('duration')
    if duration not in {None,'N/A','0','0.000000'}:
        raise ValueError('Media exceeds supported duration or dimensions')
    if not audio and max(streams[0].get('width',0),streams[0].get('height',0))>4096:
        raise ValueError('Video dimensions exceed 4096 pixels')
    temporary=path.with_suffix('.normalized.mkv')
    try:
        run(['ffmpeg','-v','error','-y','-nostdin','-protocol_whitelist','file,pipe',
            '-i',str(path),'-map','0:a:0' if audio else '0:v:0','-c','copy',
            '-t','301','-fs',str(201*1024*1024),'-f','matroska',str(temporary)],60)
        validate_media(temporary,audio)
        if temporary.stat().st_size>200*1024*1024:raise ValueError('Normalized media exceeds 200 MB')
        temporary.replace(path)
    except RuntimeError as e:
        raise ValueError('Cannot normalize uploaded recording') from e
    finally:temporary.unlink(missing_ok=True)

"""Measured layout checks, bounded repairs and sampled-frame review.

No OCR, automatic claim verification, aesthetic score or virality prediction.
A sampled still cannot establish motion/audio quality. Repairs never rewrite copy,
change claims, buy media, publish, or overwrite an adopted film.
"""
from __future__ import annotations

import base64
import io
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageStat

from .creative import CaptionLayout, CreativeSpec
from .creative_assistant import EditPlan, LayoutEdit, apply_operations
from .creative_rendering import DIMENSIONS, _lines, command, font_file, file_hash, media_info


def text_geometry(spec, scene, output, font_path=None) -> dict:
    w, h = DIMENSIONS[output]
    layout = scene.layouts.get(output, CaptionLayout())
    text = '\n'.join(l.text for l in scene.layers if l.kind == 'text')
    font_path = font_path or font_file(spec.brand.name + text + '実録画')
    size = max(12, round(min(w, h) * layout.size))
    face = ImageFont.truetype(str(font_path), size)
    draw = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    lines = _lines(draw, text, face, w * .84)
    height = len(lines) * math.ceil(size * 1.45)
    top = round(h * layout.y - height / 2)
    return {'lines': len(lines), 'top': top, 'height': height, 'size_px': size,
            'safe': len(lines) <= 5 and top >= h*.12 and top+height <= h*.94,
            'overlaps_footage': bool(text and any(l.kind in {'recording', 'generated_video'} for l in scene.layers)
                                     and top < h*.67 and top+height > h*.20)}


def inspect_layout(spec: CreativeSpec, outputs=None, scene_id=None) -> dict:
    outputs = outputs or spec.outputs
    findings = []
    for scene in spec.scenes:
        if scene_id is not None and scene.id != scene_id:
            continue
        text = '\n'.join(l.text for l in scene.layers if l.kind == 'text')
        for output in outputs:
            g = text_geometry(spec, scene, output)
            if not g['safe']:
                findings.append({'code': 'text_safe_area', 'severity': 'error', 'scene_id': scene.id,
                                 'output': output, 'message': 'Text exceeds five lines or the safe area.', 'geometry': g})
            elif g['overlaps_footage']:
                findings.append({'code': 'footage_overlap', 'severity': 'warning', 'scene_id': scene.id,
                                 'output': output, 'message': 'The caption backing overlaps the product footage; inspect readability.'})
        # An explicit heuristic, not an empirically validated attention metric.
        if len(text.replace(' ', '')) / max(scene.seconds, .5) > 15:
            findings.append({'code': 'reading_pace', 'severity': 'suggestion', 'scene_id': scene.id,
                             'output': 'all', 'message': 'Dense copy for this duration (>15 non-space characters/sec heuristic). Review the pace.'})
    return {'findings': findings, 'technical_errors': sum(f['severity']=='error' for f in findings),
            'artistic_quality': 'not_scored', 'claim_truth': 'human_review_required'}


def repair_layout(spec: CreativeSpec, max_passes: int = 3) -> tuple[EditPlan, dict]:
    """At most three local refinement passes. Only position/size may change.

    Preserve wording and footage. Keep any unresolved issues explicit instead of
    shrinking without a bound, making performance claims, or calling a provider.
    """
    if type(max_passes) is not int or not 1 <= max_passes <= 3:
        raise ValueError('Choose one to three local repair passes')
    candidate = CreativeSpec.model_validate(spec.model_dump())
    original = inspect_layout(candidate)
    used = 0
    for _ in range(max_passes):
        ops = []
        for scene in candidate.scenes:
            for output in candidate.outputs:
                g = text_geometry(candidate, scene, output)
                if g['safe'] and not g['overlaps_footage']:
                    continue
                old = scene.layouts.get(output, CaptionLayout())
                size = max(.025, round(old.size * .8, 5)) if not g['safe'] else old.size
                has_video = any(l.kind in {'recording', 'generated_video'} for l in scene.layers)
                y = .81 if has_video else .70
                ops.append(LayoutEdit(op='layout', scene_id=scene.id, output=output, y=y, size=size))
        if not ops:
            break
        candidate, changes = apply_operations(candidate, EditPlan(summary='Measured layout repair', operations=ops))
        used += 1
        if not changes:
            break
    edits = []
    for before, after in zip(spec.scenes, candidate.scenes):
        for output in spec.outputs:
            a, b = before.layouts.get(output, CaptionLayout()), after.layouts.get(output, CaptionLayout())
            if a != b:
                edits.append(LayoutEdit(op='layout', scene_id=after.id, output=output, y=b.y, size=b.size))
    final = inspect_layout(candidate)
    # Never return a repair that increases hard technical errors.
    if final['technical_errors'] > original['technical_errors']:
        edits, final = [], original
    plan = EditPlan(summary='Bounded local typography repair; review before applying.', operations=edits,
                    warnings=['No copy, media or claims were changed. Motion, audio and aesthetic quality need human review.'])
    return plan, {'before': original, 'after': final, 'passes': used, 'max_passes': max_passes,
                  'provider_calls': 0, 'unresolved': final['findings']}


def sample_frames(spec: CreativeSpec, path: Path, output: str, scene_id=None, limit=6) -> list[dict]:
    if output not in spec.outputs or not 1 <= limit <= 6:
        raise ValueError('Invalid frame sampling request')
    selected = [s for s in spec.scenes if scene_id is None or s.id == scene_id]
    if not selected:
        raise ValueError('Scene not found')
    times, cursor = [], 0
    for scene in selected:
        duration = round(scene.seconds * spec.fps) / spec.fps
        times.append((scene.id, round(cursor + duration/2, 4)))
        cursor += duration
    if len(times) > limit:
        indexes = {round(i*(len(times)-1)/(limit-1)) for i in range(limit)} if limit>1 else {0}
        times = [v for i, v in enumerate(times) if i in indexes]
    frames = []
    for sid, instant in times:
        png = command(['ffmpeg','-v','error','-nostdin','-protocol_whitelist','file,pipe',
                       '-ss',str(instant),'-i',str(path),'-frames:v','1','-vf',
                       'scale=640:640:force_original_aspect_ratio=decrease',
                       '-threads','1','-f','image2pipe','-vcodec','png','pipe:1'], timeout=30)
        if len(png) > 2*1024*1024:
            raise ValueError('Sampled frame exceeds the size limit')
        with Image.open(io.BytesIO(png)) as image:
            image.load()
            stat = ImageStat.Stat(image.convert('RGB'))
            jpeg = io.BytesIO(); image.convert('RGB').save(jpeg,format='JPEG',quality=75)
        frames.append({'scene_id':sid,'output':output,'time_seconds':instant,
                       'low_variance':max(stat.stddev)<3,
                       'data_url':'data:image/jpeg;base64,'+base64.b64encode(jpeg.getvalue()).decode('ascii')})
    return frames


def inspect_render(spec, path, output, expected_hash, scene_id=None) -> dict:
    if file_hash(path) != expected_hash:
        raise ValueError('Rendered media changed; review a new render')
    info = media_info(path)
    frames = sample_frames(spec, path, output, scene_id)
    report = inspect_layout(spec, [output], scene_id)
    report.update({'media_sha256':info['sha256'], 'output':output,
                   'samples':[{k:v for k,v in f.items() if k!='data_url'} for f in frames],
                   'sample_count':len(frames), 'motion_assessed':False, 'audio_assessed':False,
                   'note':'Low variance is a diagnostic, not a quality failure; typography may be intentionally still.'})
    return report

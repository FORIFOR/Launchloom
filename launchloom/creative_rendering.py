"""Local-only scene cache and deterministic 720p composition.

No providers, shell strings, generated code, network access or publication. The
caller supplies a frozen map of verified local assets. Unsupported layers fail
preflight rather than disappearing from the finished film.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .creative import CaptionLayout, CreativeSpec, fingerprint, scene_render_key

RENDERER_VERSION = "creative-standard-1"
DIMENSIONS = {"landscape": (1280, 720), "portrait": (720, 1280)}
MAX_BYTES = 200 * 1024 * 1024


@dataclass(frozen=True)
class Asset:
    path: Path
    sha256: str
    kind: str
    duration: float
    has_audio: bool = False
    ai_generated: bool = False


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def child(root: Path, *parts: str) -> Path:
    """All parts are server-generated, but reject symlinks at every level anyway."""
    if root.is_symlink():
        raise ValueError("Symbolic links are not allowed in creative storage")
    path = root
    for part in parts:
        if part in {"", ".", ".."} or "/" in part or "\\" in part:
            raise ValueError("Invalid creative-storage path")
        path = path / part
        if path.is_symlink():
            raise ValueError("Symbolic links are not allowed in creative storage")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Invalid creative-storage path")
    return path


def command(args: list[str], *, cwd: Path | None = None, timeout: int = 120) -> bytes:
    try:
        result = subprocess.run(args, cwd=cwd, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"{Path(args[0]).name} is unavailable or timed out") from exc
    if result.returncode:
        # Do not expose absolute paths, file contents or credentials via browser errors.
        raise ValueError(f"{Path(args[0]).name} failed; check the local media and export settings")
    return result.stdout


def media_info(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
        raise ValueError("Media is missing, linked or exceeds 200 MB")
    result = json.loads(command(["ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe",
                                "-show_format", "-show_streams", "-of", "json", str(path)], timeout=30))
    streams = result.get("streams", [])
    videos = [s for s in streams if s.get("codec_type") == "video"]
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    seconds = float(result.get("format", {}).get("duration", 0))
    if len(videos) != 1 or len(audios) > 1 or not math.isfinite(seconds) or not 0 < seconds <= 300:
        raise ValueError("Use one video track and at most one mixed audio track, up to five minutes")
    video = videos[0]
    width, height = video.get("width", 0), video.get("height", 0)
    if not 2 <= width <= 4096 or not 2 <= height <= 4096:
        raise ValueError("Unsupported video dimensions")
    return {"duration": seconds, "width": width, "height": height,
            "has_audio": bool(audios), "codec": video.get("codec_name"),
            "fps": video.get("avg_frame_rate", ""), "sha256": file_hash(path), "bytes": path.stat().st_size}


def font_file(text: str) -> Path:
    configured = os.getenv("LAUNCHLOOM_FONT_BOLD", "") or os.getenv("LAUNCHLOOM_FONT", "")
    cjk = [configured, "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
           "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc", "C:/Windows/Fonts/YuGothB.ttc"]
    candidates = cjk if re.search(r"[\u3000-\u9fff\uac00-\ud7af]", text) else cjk + [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc", "C:/Windows/Fonts/arialbd.ttf"]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise ValueError("Install a font covering your copy (for Japanese: Noto Sans CJK) or configure LAUNCHLOOM_FONT_BOLD")


def preflight(spec: CreativeSpec, assets: dict[str, Asset], scene_id: str | None = None) -> list[dict]:
    scenes = [s for s in spec.scenes if scene_id is None or s.id == scene_id]
    if not scenes:
        return [{"scene_id": scene_id, "message": "Scene not found"}]
    problems = []
    for scene in scenes:
        errors = []
        if scene.camera not in {"hold", "gentle_zoom"}:
            errors.append("The standard renderer supports hold/gentle_zoom; use the legacy capture renderer for action tracking")
        if len([x for x in scene.layers if x.kind in {"recording", "generated_video"}]) > 1:
            errors.append("The standard renderer supports one video per scene")
        if len([x for x in scene.layers if x.kind == "text"]) > 3:
            errors.append("The standard renderer supports up to three text layers")
        for layer in scene.layers:
            if layer.kind in {"image", "audio"}:
                errors.append(f"Separate {layer.kind} layers need another renderer; they are not silently omitted")
            if layer.kind not in {"recording", "generated_video"}:
                continue
            asset = assets.get(layer.asset_id)
            if not asset:
                errors.append(f"Choose prepared media for layer {layer.id}; rendering never generates or charges for missing footage")
                continue
            if not layer.asset_sha256 or layer.asset_sha256 != asset.sha256:
                errors.append(f"Media for {layer.id} changed; select and review it again")
            if layer.role == "evidence" and (asset.kind != "recording" or asset.ai_generated):
                errors.append("Generated or declared-AI media cannot be product evidence")
            if layer.kind != asset.kind:
                errors.append("The layer kind does not match the registered media provenance")
            if layer.start_seconds + round(scene.seconds * spec.fps) / spec.fps > asset.duration + 0.02:
                errors.append(f"Media is too short for {layer.id}; shorten the scene or choose longer footage")
        problems.extend({"scene_id": scene.id, "message": message} for message in errors)
    return problems


def _lines(draw, text, font, width):
    lines, line = [], ""
    # Deterministic Unicode wrapping; never truncate copy or replace it with ellipses.
    for char in text:
        if char == "\n":
            lines.append(line); line = ""; continue
        if line and draw.textlength(line + char, font=font) > width:
            lines.append(line); line = ""
        line += char
    if line:
        lines.append(line)
    return lines


def artwork(spec, scene, output, root, font_path, has_video, generated):
    w, h = DIMENSIONS[output]
    palette = {"editorial": ("#F6F5F0", "#20251F", "#DADCD3"),
               "spotlight": ("#171A17", "#F6F5F0", "#303830"),
               "grid": ("#EDF3ED", "#172B29", "#CEDDCF")}[spec.brand.preset]
    bg, ink, rule = palette
    base = Image.new("RGB", (w, h), bg)
    draw = ImageDraw.Draw(base)
    if spec.brand.preset == "grid":
        for x in range(0, w, 48): draw.line((x, 0, x, h), fill=rule)
        for y in range(0, h, 48): draw.line((0, y, w, y), fill=rule)
    margin = int(w * 0.07)
    small = ImageFont.truetype(str(font_path), max(14, int(min(w, h) * 0.024)))
    # A bounded identifier remains readable even with an 80-character brand name.
    brand_lines = _lines(draw, spec.brand.name, small, w * 0.70)
    for i, text in enumerate(brand_lines[:3]):
        draw.text((margin, h * 0.055 + i * small.size * 1.2), text, font=small, fill=ink)
    draw.rectangle((w - margin - 32, h * 0.065, w - margin, h * 0.065 + 4), fill=spec.brand.accent)
    box = (margin, int(h * 0.20), w - 2 * margin, int(h * 0.47))
    if has_video:
        x, y, bw, bh = box
        draw.rounded_rectangle((x - 1, y - 1, x + bw + 1, y + bh + 1), radius=12, fill="#171A17")
        label = "生成イメージ / CONCEPT" if generated else "実録画 / RECORDED PRODUCT"
        draw.text((margin, y + bh + 12), label, font=small, fill=ink)
    elif spec.brand.preset == "spotlight":
        draw.line((margin, h * 0.34, w * 0.42, h * 0.34), fill=spec.brand.accent, width=3)
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    text_draw = ImageDraw.Draw(overlay)
    layout = scene.layouts.get(output, CaptionLayout())
    size = max(12, round(min(w, h) * layout.size))
    face = ImageFont.truetype(str(font_path), size)
    text = "\n".join(x.text for x in scene.layers if x.kind == "text")
    lines = _lines(text_draw, text, face, w * 0.84)
    if len(lines) > 5:
        raise ValueError(f"{scene.id}/{output}: copy needs more than five lines; shorten it or reduce text size")
    line_height = math.ceil(size * 1.45)
    top = round(h * layout.y - len(lines) * line_height / 2)
    if top < h * 0.12 or top + len(lines) * line_height > h * 0.94:
        raise ValueError(f"{scene.id}/{output}: text exceeds the safe area; adjust position or size")
    # Opaque backing maintains readability when the operator moves text over footage.
    if text:
        text_draw.rounded_rectangle((margin - 8, top - 10, w - margin + 8, top + len(lines) * line_height + 10),
                                    radius=8, fill=bg)
    for i, line in enumerate(lines):
        width = text_draw.textlength(line, font=face)
        text_draw.text(((w - width) / 2, top + i * line_height), line, font=face, fill=ink)
    base.save(root / "ground.png"); overlay.save(root / "type.png")
    return box


def render_scene(spec, scene, output, assets, folder, font_path):
    folder.mkdir(parents=True, exist_ok=True)
    footage = next((x for x in scene.layers if x.kind in {"recording", "generated_video"}), None)
    asset = assets.get(footage.asset_id) if footage else None
    box = artwork(spec, scene, output, folder, font_path, bool(asset), bool(asset and (asset.ai_generated or asset.kind == "generated_video")))
    w, h = DIMENSIONS[output]
    frames = round(scene.seconds * spec.fps)
    duration = frames / spec.fps
    args = ["ffmpeg", "-v", "error", "-nostdin", "-y", "-filter_complex_threads", "1",
            "-loop", "1", "-framerate", str(spec.fps), "-i", str(folder / "ground.png")]
    filters = []
    if asset:
        args += ["-protocol_whitelist", "file,pipe", "-ss", str(footage.start_seconds), "-i", str(asset.path)]
        x, y, bw, bh = box
        bw -= bw % 2; bh -= bh % 2
        zoom = (f",zoompan=z='1+0.025*on/{max(frames - 1, 1)}':x='iw/2-iw/zoom/2':"
                f"y='ih/2-ih/zoom/2':d=1:s={bw}x{bh}:fps={spec.fps}") if scene.camera == "gentle_zoom" else ""
        filters.append(f"[1:v]setpts=PTS-STARTPTS,fps={spec.fps},scale={bw}:{bh}:force_original_aspect_ratio=decrease,"
                       f"pad={bw}:{bh}:(ow-iw)/2:(oh-ih)/2,setsar=1{zoom}[footage]")
        filters.append(f"[0:v][footage]overlay={x}:{y}:shortest=1[stage]")
        text_index = 2
    else:
        filters.append("[0:v]null[stage]")
        text_index = 1
    args += ["-loop", "1", "-framerate", str(spec.fps), "-i", str(folder / "type.png")]
    fade = min(0.25, duration / 4)
    filters.append(f"[{text_index}:v]format=rgba,fade=t=in:st=0:d={fade}:alpha=1,"
                   f"fade=t=out:st={duration-fade}:d={fade}:alpha=1[type]")
    filters.append("[stage][type]overlay=0:0:shortest=1,format=yuv420p[v]")
    if asset and asset.has_audio:
        audio = "1:a:0"
    else:
        audio = f"{text_index + 1}:a:0"
        args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    target = folder / "scene.mp4"
    args += ["-filter_complex", ";".join(filters), "-map", "[v]", "-map", audio,
             "-af", "apad", "-t", str(duration), "-frames:v", str(frames), "-r", str(spec.fps),
             "-c:v", "libx264", "-preset", "fast", "-crf", "19", "-threads", "2",
             "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "160k",
             "-map_metadata", "-1", "-movflags", "+faststart", "-fs", str(MAX_BYTES + 1), str(target)]
    command(args, timeout=180)
    info = media_info(target)
    if (info["width"], info["height"]) != (w, h) or abs(info["duration"] - duration) > 0.16:
        raise ValueError("Scene render did not match its dimensions or duration")
    return target, info


def render_project(spec: CreativeSpec, assets: dict[str, Asset], cache: Path, destination: Path,
                   *, scene_id: str | None = None, outputs: list[str] | None = None, progress=None) -> dict:
    outputs = outputs or spec.outputs
    if not outputs or len(outputs) != len(set(outputs)) or any(o not in spec.outputs for o in outputs):
        raise ValueError("Choose unique enabled outputs")
    issues = preflight(spec, assets, scene_id)
    if issues:
        raise ValueError("; ".join(f"{x['scene_id']}: {x['message']}" for x in issues)[:1200])
    if cache.is_symlink() or destination.is_symlink():
        raise ValueError("Linked rendering directories are not allowed")
    cache.mkdir(parents=True, exist_ok=True); destination.mkdir(parents=True, exist_ok=True)
    selected = [s for s in spec.scenes if scene_id is None or s.id == scene_id]
    text = spec.brand.name + "".join(l.text for s in selected for l in s.layers) + "実録画 生成イメージ"
    font_path = font_file(text)
    version = RENDERER_VERSION + command(["ffmpeg", "-version"], timeout=10).decode().splitlines()[0]
    catalog = {key: {"sha256": value.sha256} for key, value in assets.items()}
    font_digest = file_hash(font_path)
    # Freeze only assets used in this render. Verify before and after copying.
    frozen = {}
    for aid in {x.asset_id for s in selected for x in s.layers if x.asset_id}:
        original = assets[aid]
        if original.path.is_symlink() or file_hash(original.path) != original.sha256:
            raise ValueError("Source media changed; review it before rendering")
        target = child(destination, f"asset-{original.sha256}.bin")
        shutil.copyfile(original.path, target)
        if file_hash(target) != original.sha256:
            raise ValueError("Source media changed while it was being copied")
        frozen[aid] = Asset(target, original.sha256, original.kind, original.duration,
                            original.has_audio, original.ai_generated)
    reports = []
    result = {}
    total = len(outputs) * len(selected)
    for output in outputs:
        assembled = child(destination, output)
        assembled.mkdir(exist_ok=True)
        for index, scene in enumerate(selected):
            key = scene_render_key(spec, scene, output, catalog, version, font_digest)
            video, metadata = child(cache, key + ".mp4"), child(cache, key + ".json")
            reused = False
            if video.is_file() and metadata.is_file():
                try:
                    cached = json.loads(metadata.read_text())
                    reused = cached["sha256"] == file_hash(video) and cached["key"] == key
                except (OSError, ValueError, KeyError):
                    pass
            if not reused:
                work = child(destination, "scene-" + uuid.uuid4().hex)
                try:
                    built, info = render_scene(spec, scene, output, frozen, work, font_path)
                    os.replace(built, video)
                    temp = child(cache, key + ".tmp")
                    temp.write_text(json.dumps({**info, "key": key}), encoding="utf-8")
                    os.replace(temp, metadata)
                finally:
                    shutil.rmtree(work, ignore_errors=True)
            segment = assembled / f"{index:03}.mp4"
            shutil.copyfile(video, segment)
            if file_hash(segment) != json.loads(metadata.read_text())["sha256"]:
                raise ValueError("Cached scene changed during assembly")
            reports.append({"scene_id": scene.id, "output": output, "reused": reused, "key": key})
            if progress: progress(len(reports), total)
        listing = assembled / "concat.txt"
        listing.write_text("".join(f"file {i:03}.mp4\n" for i in range(len(selected))), encoding="utf-8")
        final = child(destination, output + ".mp4")
        duration = sum(round(s.seconds * spec.fps) for s in selected) / spec.fps
        command(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "concat", "-safe", "1",
                 "-i", str(listing), "-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy",
                 "-c:a", "aac", "-af", "apad", "-ar", "48000", "-ac", "2", "-t", str(duration),
                 "-map_metadata", "-1", "-movflags", "+faststart", "-fs", str(MAX_BYTES + 1), str(final)], timeout=180)
        info = media_info(final)
        if abs(info["duration"] - duration) > 0.16 or (info["width"], info["height"]) != DIMENSIONS[output]:
            raise ValueError("Assembly failed technical QA")
        command(["ffmpeg", "-v", "error", "-nostdin", "-xerror", "-threads", "2", "-i", str(final),
                 "-f", "null", "-"], timeout=180)
        result[output] = info
        shutil.rmtree(assembled)
    # Snapshot files have served their purpose; cached composed scenes remain reusable.
    for path in {a.path for a in frozen.values()}: path.unlink(missing_ok=True)
    return {"outputs": result, "scenes": reports, "scene_id": scene_id,
            "qa": {"full_decode": True, "dimensions": True, "duration": True, "text_safe_area": True,
                   "artistic_quality": "not_assessed", "claim_truth": "operator_review_required"},
            "provider_called": False, "published": False}

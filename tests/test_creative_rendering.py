import copy
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from launchloom.creative import (BrandProfile, CaptionLayout, CreativeLayer, CreativeScene,
                                CreativeSpec, creative_revision, scene_render_key)
from launchloom.creative_edits import propose_edit
from launchloom.creative_rendering import Asset, child, file_hash, media_info, preflight, render_project


def spec():
    return CreativeSpec(title="A film", brand=BrandProfile(name="Launchloom"), scenes=[
        CreativeScene(id="opening", purpose="hook", seconds=.6,
                      layers=[CreativeLayer(id="copy", kind="text", role="copy", text="Make the moment matter.")]),
        CreativeScene(id="closing", purpose="cta", seconds=.6,
                      layers=[CreativeLayer(id="copy", kind="text", role="copy", text="Keep what works.")])])


def change(value, mutate):
    data = copy.deepcopy(value.model_dump()); mutate(data)
    return CreativeSpec.model_validate(data)


@pytest.mark.parametrize("value", [True, False, "3", float("nan"), float("inf"), -1, 31])
def test_duration_is_finite_and_numeric(value):
    with pytest.raises(ValueError):
        change(spec(), lambda d: d["scenes"][0].update(seconds=value))


@pytest.mark.parametrize("kind", ["generated_video", "text", "shape", "image", "audio"])
def test_only_recorded_layers_can_be_evidence(kind):
    with pytest.raises(ValueError):
        CreativeLayer(id="fake", kind=kind, role="evidence", asset_id="clip", text="Claim", generator="model")


@pytest.mark.parametrize("fps", [True, "30", 30.0, 60])
def test_fps_has_an_integer_contract(fps):
    with pytest.raises(ValueError): change(spec(), lambda d: d.update(fps=fps))


@pytest.mark.parametrize("value", ["../secret", "/tmp/media", "a/b", "a\\b", "https://example.com"])
def test_asset_reference_is_not_a_path(value):
    with pytest.raises(ValueError):
        CreativeLayer(id="product", kind="recording", role="evidence", asset_id=value)


def test_revision_stable_under_key_order_and_brand_changes():
    value = spec(); data = value.model_dump()
    assert creative_revision(value) == creative_revision(dict(reversed(list(data.items()))))
    newer = change(value, lambda d: d["brand"].update(preset="spotlight"))
    assert creative_revision(value) != creative_revision(newer)


def key(value, output="landscape"):
    return scene_render_key(value, value.scenes[0], output, {}, "renderer1", "font1")


def test_cache_includes_globals_but_not_other_aspect_or_scene_order():
    original = spec()
    portrait = change(original, lambda d: d["scenes"][0].update(layouts={"portrait": {"y": .60, "size": .04}}))
    assert key(original) == key(portrait)
    assert key(original, "portrait") != key(portrait, "portrait")
    for mutation in [lambda d: d["brand"].update(preset="grid"), lambda d: d.update(fps=24),
                     lambda d: d["brand"].update(motion_direction="Different production intent")]:
        assert key(original) != key(change(original, mutation))
    reordered = change(original, lambda d: d["scenes"].reverse())
    assert key(original) == scene_render_key(reordered, reordered.scenes[1], "landscape", {}, "renderer1", "font1")
    assert key(original) != scene_render_key(original, original.scenes[0], "landscape", {}, "renderer2", "font1")
    assert key(original) != scene_render_key(original, original.scenes[0], "landscape", {}, "renderer1", "font2")


@pytest.mark.parametrize("instruction,field,expected", [("2秒にする", "seconds", 2), ("set to 3", "seconds", 3)])
def test_explicit_edit_does_not_mutate_or_save(instruction, field, expected):
    original = spec(); before = original.model_dump()
    result = propose_edit(original, "opening", instruction, "portrait")
    assert result["spec"]["scenes"][0][field] == expected
    assert original.model_dump() == before
    assert result["saved"] is False and result["provider_called"] is False


def test_move_text_only_changes_selected_aspect():
    result = propose_edit(spec(), "opening", "文字を上へ", "portrait")
    layouts = result["spec"]["scenes"][0]["layouts"]
    assert layouts["portrait"]["y"] == pytest.approx(.70)
    assert "landscape" not in layouts


@pytest.mark.parametrize("instruction", ["rm -rf /", "send to social", "make it viral", "2秒短く", "31秒にする", "NaN秒にする"])
def test_unknown_or_out_of_bounds_edits_fail(instruction):
    with pytest.raises(ValueError): propose_edit(spec(), "opening", instruction, "portrait")


def test_missing_generation_is_a_blocker_not_a_provider_request():
    value = spec().model_dump()
    value["scenes"][0]["layers"].append({"id": "atmosphere", "kind": "generated_video", "role": "concept", "generator": "seedance"})
    value = CreativeSpec.model_validate(value)
    assert "never generates" in preflight(value, {})[0]["message"]
    assert preflight(value, {}, scene_id="closing") == []


def test_symlink_rejected_at_each_level(tmp_path):
    (tmp_path / "outside").mkdir(); (tmp_path / "cache").symlink_to(tmp_path / "outside", target_is_directory=True)
    with pytest.raises(ValueError): child(tmp_path, "cache", "file.mp4")
    with pytest.raises(ValueError): child(tmp_path, "..", "file.mp4")


media = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg required")


@media
def test_real_two_format_render_and_partial_reuse(tmp_path):
    value = spec(); cache = tmp_path / "cache"
    first = render_project(value, {}, cache, tmp_path / "one")
    assert {(x["width"], x["height"]) for x in first["outputs"].values()} == {(1280, 720), (720, 1280)}
    assert first["qa"]["full_decode"] is True
    assert not first["provider_called"] and not first["published"]
    again = render_project(value, {}, cache, tmp_path / "two")
    assert all(x["reused"] for x in again["scenes"])
    changed = change(value, lambda d: d["scenes"][0]["layers"][0].update(text="One changed scene."))
    third = render_project(changed, {}, cache, tmp_path / "three")
    assert {x["scene_id"] for x in third["scenes"] if not x["reused"]} == {"opening"}
    portrait = change(changed, lambda d: d["scenes"][0].update(layouts={"portrait": {"y": .65, "size": .04}}))
    fourth = render_project(portrait, {}, cache, tmp_path / "four")
    assert [(x["scene_id"], x["output"]) for x in fourth["scenes"] if not x["reused"]] == [("opening", "portrait")]
    reversed_spec = change(portrait, lambda d: d["scenes"].reverse())
    fifth = render_project(reversed_spec, {}, cache, tmp_path / "five")
    assert all(x["reused"] for x in fifth["scenes"])
    assert fifth["outputs"]["landscape"]["sha256"] != fourth["outputs"]["landscape"]["sha256"]


@media
def test_corrupt_cache_is_not_reused(tmp_path):
    value = spec(); cache = tmp_path / "cache"
    first = render_project(value, {}, cache, tmp_path / "one", scene_id="closing", outputs=["landscape"])
    (cache / (first["scenes"][0]["key"] + ".mp4")).write_bytes(b"changed")
    second = render_project(value, {}, cache, tmp_path / "two", scene_id="closing", outputs=["landscape"])
    assert second["scenes"][0]["reused"] is False


@media
def test_recording_audio_and_source_digest_are_preserved(tmp_path):
    source = tmp_path / "recording.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "1.5",
                    "-c:v", "libx264", "-threads", "2", "-c:a", "aac", str(source)], check=True)
    info = media_info(source)
    asset = Asset(source, info["sha256"], "recording", info["duration"], True)
    value = spec().model_dump()
    value["scenes"][0].update(purpose="proof", claim_ids=["feature-0"], camera="gentle_zoom")
    value["scenes"][0]["layers"].insert(0, {"id": "product", "kind": "recording", "role": "evidence",
                   "asset_id": "capture", "asset_sha256": info["sha256"], "start_seconds": .2})
    value = CreativeSpec.model_validate(value)
    assert preflight(value, {"capture": asset}) == []
    output = tmp_path / "out"
    result = render_project(value, {"capture": asset}, tmp_path / "cache", output, scene_id="opening", outputs=["landscape"])
    assert result["outputs"]["landscape"]["has_audio"]
    volume = subprocess.run(["ffmpeg", "-i", str(output / "landscape.mp4"), "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
    assert "max_volume: -inf" not in volume.stderr and "max_volume:" in volume.stderr
    source.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="changed"):
        render_project(value, {"capture": asset}, tmp_path / "cache", tmp_path / "again", scene_id="opening", outputs=["landscape"])


@media
def test_copy_is_not_silently_truncated(tmp_path):
    value = change(spec(), lambda d: d["scenes"][0]["layers"][0].update(text="LONG COPY " * 40))
    with pytest.raises(ValueError, match="five lines"):
        render_project(value, {}, tmp_path / "cache", tmp_path / "out", scene_id="opening", outputs=["portrait"])

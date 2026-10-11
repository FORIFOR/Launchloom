"""Export/deployment contracts for template notices, without provider or browser calls."""
import asyncio
import hashlib
import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from launchloom import creative_package, deploy, pipeline
from launchloom.config import Settings
from launchloom.creative import CreativeSpec
from launchloom.models import Brief, BuildOptions
from launchloom.output_licenses import LICENSE_FILES, TEMPLATE_MODIFICATION_NOTICE
from launchloom.security import file_sha
from launchloom.site import build_site
from launchloom.store import Store


PRIVATE = "PRIVATE-EVIDENCE-REFERENCE-AND-RAW-INPUT-DO-NOT-EXPORT"
NOTICES = {"LICENSE", "NOTICE", "site/LICENSE", "site/NOTICE"}


@pytest.fixture
def brief():
    return Brief(name="Local demo", tagline="One useful feature", audience="Creators",
                 language="en", references=[PRIVATE], features=[{
                     "title": "Approved feature", "detail": "An approved description.",
                     "evidence": PRIVATE, "approved": True}])


def poster(path):
    image = Image.new("RGB", (32, 32), "black")
    image.paste("white", (16, 0, 32, 32))
    image.save(path)


def assert_notices(folder):
    original_license = (Path(__file__).resolve().parents[1] / "LICENSE").read_bytes()
    for name in ("LICENSE", "site/LICENSE"):
        assert (folder / name).read_bytes() == original_license
    notice = (folder / "NOTICE").read_text()
    assert (folder / "site/NOTICE").read_text() == notice
    assert "Original application source and templates are licensed under Apache-2.0." in notice
    assert "does not relicense or clear rights to customer copy" in notice
    assert "not the entire generated launch kit" in notice
    assert "No reference-post videos, licensed music" not in notice
    assert TEMPLATE_MODIFICATION_NOTICE in (folder / "site/index.html").read_text()


def assert_archive(archive, manifest, expected):
    with zipfile.ZipFile(archive) as kit:
        assert kit.testzip() is None
        assert set(kit.namelist()) == expected | NOTICES | {"manifest.json"}
        assert set(manifest["files"]) == expected | NOTICES
        assert json.loads(kit.read("manifest.json")) == manifest
        for name, entry in manifest["files"].items():
            content = kit.read(name)
            assert PRIVATE.encode() not in content
            checksum = entry["sha256"] if isinstance(entry, dict) else entry
            assert hashlib.sha256(content).hexdigest() == checksum
            if isinstance(entry, dict):
                assert len(content) == entry["bytes"]


def test_standard_kit_includes_scoped_notices_and_excludes_private_files(tmp_path, brief, monkeypatch):
    settings = Settings(data_dir=tmp_path / "data", token="local-test-token-with-enough-characters")
    settings.prepare()
    store = Store(tmp_path / "state.db")
    cid = store.create_campaign(brief.model_dump())["id"]
    root = settings.data_dir / "campaigns" / cid
    for name in ("input/customer.txt", "capture/raw.webm", "site/private.txt", "access-token"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(PRIVATE)

    def render(*args):
        for output in ("landscape", "portrait"):
            (root / (output + ".mp4")).write_bytes(b"approved rendered output")
            poster(root / (output + ".jpg"))
        return {output: {"duration": 15} for output in ("landscape", "portrait")}

    monkeypatch.setattr(pipeline, "render", render)
    manifest = asyncio.run(pipeline.build(settings, store, cid, BuildOptions()))
    assert_notices(root)
    assert_archive(root / "launch-kit.zip", manifest, {
        "campaign.json", "storyboard.json", "posts.json", "social-copy.md", "captions.srt",
        "qa.json", "landscape.mp4", "portrait.mp4", "landscape.jpg", "portrait.jpg",
        "site/index.html", "site/site.css", "site/site.js", "site/film.mp4", "site/poster.jpg"})
    assert store.campaign(cid)["state"] == "ready"
    assert (root / "brief.json").is_file()  # Private input exists, but is not exported.


@pytest.mark.parametrize("outputs", [["portrait"], ["landscape", "portrait"]])
def test_creative_kit_includes_scoped_notices_and_excludes_private_files(tmp_path, brief, monkeypatch, outputs):
    spec = CreativeSpec(title="Approved film", outputs=outputs,
                        brand={"name": brief.name, "visual_direction": PRIVATE}, scenes=[{
                            "id": "opening", "purpose": "hook", "seconds": 2,
                            "layers": [{"id": "title", "kind": "text", "role": "copy",
                                        "text": "Approved headline"}]}])
    sources = {}
    for output in outputs:
        source = tmp_path / (output + ".mp4")
        source.write_bytes(b"approved rendered " + output.encode())
        sources[output] = (source, file_sha(source))
    monkeypatch.setattr(creative_package, "command", lambda args, **kwargs: poster(Path(args[-1])))
    folder = tmp_path / "kit"
    manifest = creative_package.write_package(spec, brief, "campaign", sources, folder)
    assert_notices(folder)
    assert TEMPLATE_MODIFICATION_NOTICE in (folder / "site/site.css").read_text()
    for name in ("creative-spec.json", "input.txt", "site/private.txt"):
        (folder / name).write_text(PRIVATE)
    archive = folder / "launch-kit.zip"
    creative_package.zip_package(folder, archive)
    assert_archive(archive, manifest, {
        "README.txt", "copy.json", "captions.srt", "posts.json", "social-copy.md",
        "poster.jpg", "site/index.html", "site/site.css", *(output + ".mp4" for output in outputs)})


@pytest.fixture
def deployment(tmp_path, brief):
    target = tmp_path / "public"
    target.mkdir()
    settings = Settings(data_dir=tmp_path / "data", deploy_dir=str(target), token="local-test-token")
    root = settings.data_dir / "campaigns" / "campaign"
    site = root / "site"
    build_site(brief, "campaign", site, settings, has_film=True)
    (site / "film.mp4").write_bytes(b"approved rendered film")
    poster(site / "poster.jpg")
    (site / "private.txt").write_text(PRIVATE)
    (root / "brief.json").write_text(PRIVATE)
    (target / "CNAME").write_text("example.test")
    return root, settings, target


def test_approved_deployment_copies_and_fingerprints_notices_without_private_data(deployment):
    root, settings, target = deployment
    preview = deploy.plan(root, settings)
    expected = {"index.html", "site.css", "site.js", "film.mp4", "poster.jpg", "LICENSE", "NOTICE"}
    assert {entry["name"] for entry in preview["files"]} == expected
    for entry in preview["files"]:
        assert entry["sha256"] == file_sha(root / "site" / entry["name"])
    result = deploy.publish(root, settings, preview["fingerprint"])
    assert set(result["written"]) == expected
    assert {p.name for p in target.iterdir()} == expected | {"CNAME"}
    for name in expected:
        assert (target / name).read_bytes() == (root / "site" / name).read_bytes()
        assert PRIVATE.encode() not in (target / name).read_bytes()
    assert (target / "CNAME").read_text() == "example.test"
    assert {entry["status"] for entry in deploy.plan(root, settings)["files"]} == {"unchanged"}


@pytest.mark.parametrize("name", LICENSE_FILES)
def test_changed_notice_invalidates_deployment_approval(deployment, name):
    root, settings, target = deployment
    preview = deploy.plan(root, settings)
    with (root / "site" / name).open("a") as notice:
        notice.write("\nChanged after approval\n")
    with pytest.raises(ValueError, match="changed since it was previewed"):
        deploy.publish(root, settings, preview["fingerprint"])
    assert {p.name for p in target.iterdir()} == {"CNAME"}


@pytest.mark.parametrize("name", LICENSE_FILES)
def test_deployment_requires_notices(deployment, name):
    root, settings, _ = deployment
    (root / "site" / name).unlink()
    with pytest.raises(ValueError, match="missing " + name + "; regenerate it with this version"):
        deploy.plan(root, settings)
    assert not (root / "site" / name).exists()  # Preview must not migrate old exports.


@pytest.mark.parametrize("name", LICENSE_FILES)
def test_deployment_refuses_notice_destination_symlinks(deployment, tmp_path, name):
    root, settings, target = deployment
    elsewhere = tmp_path / "unrelated"
    elsewhere.write_text("keep this")
    (target / name).symlink_to(elsewhere)
    with pytest.raises(ValueError, match="symlink"):
        deploy.plan(root, settings)
    assert elsewhere.read_text() == "keep this"

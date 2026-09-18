import copy
import pytest

from launchloom.creative import (
    CreativeLayer,
    CreativeScene,
    CreativeSpec,
    BrandProfile,
    changed_scene_ids,
    creative_revision,
    from_production_plan,
)
from launchloom.production import initial_plan


def legacy():
    brief = {
        "name": "Sample",
        "tagline": "Ship the work",
        "audience": "small product teams",
        "features": [
            {"title": "Real capture", "approved": True, "evidence": "operator verified"},
            {"title": "Not public", "approved": False, "evidence": ""},
        ],
    }
    return brief, initial_plan(brief)


def test_legacy_adapter_separates_tool_from_scene_layers():
    brief, plan = legacy()
    spec = from_production_plan(plan, brief)
    assert spec.schema_version == 2
    assert spec.outputs == ["landscape", "portrait"]
    proof = next(scene for scene in spec.scenes if scene.id == "product")
    assert proof.purpose == "proof"
    assert [layer.kind for layer in proof.layers] == ["recording", "text"]
    assert proof.layers[0].role == "evidence"
    assert proof.claim_ids == ["feature-0"]


def test_generated_video_cannot_be_product_evidence():
    with pytest.raises(ValueError):
        CreativeLayer(id="fake", kind="generated_video", role="evidence", generator="seedance")


def test_proof_requires_evidence_layer():
    with pytest.raises(ValueError):
        CreativeScene(
            id="proof", purpose="proof", seconds=3,
            layers=[CreativeLayer(id="copy", kind="text", role="copy", text="Claim")]
        )


def test_revision_is_stable_and_scene_diff_is_local():
    brief, plan = legacy()
    before = from_production_plan(plan, brief)
    clone = CreativeSpec.model_validate(before.model_dump())
    assert creative_revision(before) == creative_revision(clone)

    data = copy.deepcopy(before.model_dump())
    data["scenes"][0]["layers"][1]["text"] = "A tighter opening"
    after = CreativeSpec.model_validate(data)
    assert creative_revision(before) != creative_revision(after)
    assert changed_scene_ids(before, after) == {"opening"}


def test_brand_change_does_not_falsely_mark_all_scenes_changed():
    brief, plan = legacy()
    before = from_production_plan(plan, brief)
    data = copy.deepcopy(before.model_dump())
    data["brand"]["motion_direction"] = "Faster, but still restrained."
    after = CreativeSpec.model_validate(data)
    assert changed_scene_ids(before, after) == set()


def test_duplicate_scene_and_layer_ids_are_rejected():
    brand = BrandProfile(name="Sample")
    scene = CreativeScene(
        id="opening", purpose="hook", seconds=2,
        layers=[CreativeLayer(id="copy", kind="text", role="copy", text="Hello")],
    )
    with pytest.raises(ValueError):
        CreativeSpec(title="x", brand=brand, scenes=[scene, scene])
    with pytest.raises(ValueError):
        CreativeScene(
            id="opening", purpose="hook", seconds=2,
            layers=[
                CreativeLayer(id="copy", kind="text", role="copy", text="A"),
                CreativeLayer(id="copy", kind="text", role="copy", text="B"),
            ],
        )

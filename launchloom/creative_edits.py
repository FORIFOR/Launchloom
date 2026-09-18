"""Small explicit editing vocabulary, not an LLM and never executable code."""
from __future__ import annotations
import re
from .creative import CaptionLayout, CreativeSpec


def propose_edit(spec: CreativeSpec, scene_id: str, instruction: str, output: str) -> dict:
    if output not in spec.outputs:
        raise ValueError("Choose an enabled aspect ratio")
    instruction = instruction.strip()
    if not 1 <= len(instruction) <= 300:
        raise ValueError("Use an instruction of 1–300 characters")
    data = spec.model_dump()
    scene = next((x for x in data["scenes"] if x["id"] == scene_id), None)
    if scene is None:
        raise ValueError("Scene not found")
    action = ""
    duration = re.fullmatch(r"(?:([0-9]+(?:\.[0-9]+)?)秒に(?:する)?|set (?:duration )?to ([0-9]+(?:\.[0-9]+)?))", instruction, re.I)
    shorten = re.fullmatch(r"(?:([0-9]+(?:\.[0-9]+)?)秒短く|shorten by ([0-9]+(?:\.[0-9]+)?))", instruction, re.I)
    if duration or shorten:
        match = duration or shorten
        value = float(next(x for x in match.groups() if x is not None))
        scene["seconds"] = value if duration else scene["seconds"] - value
        action = "duration"
    elif instruction.lower() in {"文字を上へ", "文字を下へ", "text higher", "text lower"}:
        layout = scene["layouts"].get(output, CaptionLayout().model_dump())
        layout["y"] += -0.08 if instruction.lower() in {"文字を上へ", "text higher"} else 0.08
        scene["layouts"][output] = layout
        action = "caption_position"
    else:
        raise ValueError("Supported: 5秒にする / 2秒短く / 文字を上へ / 文字を下へ (or set to 5 / shorten by 2 / text higher / text lower)")
    candidate = CreativeSpec.model_validate(data)
    return {"spec": candidate.model_dump(), "scene_id": scene_id, "action": action,
            "saved": False, "provider_called": False}

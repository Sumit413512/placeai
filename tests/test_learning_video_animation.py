"""Regression coverage for original PlaceAI concept animation storyboards."""
from hashlib import sha256

import pytest
from PIL import ImageChops
from pydantic import ValidationError

from app.learning_video_animation import animated_frame
from app.learning_video_content import VideoScene, VideoStoryboard
from app.learning_video_media import (BRAND_LOGO_PATH, BRAND_SAFE_BOX,
                                      board_frame, inspect_video, render_video, slide)


def animated_scene(kind="array"):
    visual = {
        "kind": kind,
        "labels": ["8", "6", "9", "7"] if kind != "bar_chart"
                  else ["Linear", "Binary", "Hash", "Tree"],
        "focus_index": 3,
        "action": "scan",
        "takeaway": "Index 3 contains the value 7",
    }
    if kind == "bar_chart":
        visual["values"] = [100, 12, 3, 41]
        visual["takeaway"] = "Illustrative relative costs; smaller is faster"
    if kind == "code_trace":
        visual["labels"] = ["int i = 0;", "while (i < 4) {", "    i++;", "}"]
        visual["takeaway"] = "The loop increments i"
    return {
        "title": "A visual walk through the algorithm",
        "narration": ("Start with four values, then observe how the highlighted "
                      "position moves through the sequence. We keep the original "
                      "order, track each index, and show the final selected value "
                      "before interpreting what the algorithm does."),
        "bullets": ["Follow the actual data path"],
        "code": "",
        "diagram": None,
        "visual": visual,
        "source_ids": [1],
    }


@pytest.mark.parametrize("kind", [
    "array", "linked_list", "bar_chart", "flow", "timeline", "compare", "code_trace"])
def test_animated_visuals_change_in_the_teaching_area(kind):
    scene = VideoScene.model_validate(animated_scene(kind)).model_dump()
    early = animated_frame(scene, 1, 7, .08)
    late = animated_frame(scene, 1, 7, .92)
    assert early.size == (960, 540)
    assert late.size == early.size
    assert ImageChops.difference(
        early.crop((55, 195, 905, 440)), late.crop((55, 195, 905, 440))).getbbox()
    assert ImageChops.difference(
        early.crop(BRAND_SAFE_BOX), late.crop(BRAND_SAFE_BOX)).getbbox() is None


def test_animated_frame_preserves_exact_supplied_logo_asset():
    assert sha256(BRAND_LOGO_PATH.read_bytes()).hexdigest() == (
        "9f40f815509927ab2580f6e2f090a3ce19c0db8262841e1e925515b504c4c854")
    scene = animated_scene()
    first = slide(scene, 1, 4)
    for phase in (0, .1, .4, .7, 1):
        frame = board_frame(scene, 1, 4, phase)
        assert not ImageChops.difference(
            first.crop(BRAND_SAFE_BOX), frame.crop(BRAND_SAFE_BOX)).getbbox()
        pixels = list(frame.crop(BRAND_SAFE_BOX).getdata())
        assert sum(r > 185 and g > 185 and b > 185 for r, g, b in pixels) > 900
        assert sum(b > 105 and b > r * 1.18 and b > g * 1.08 for r, g, b in pixels) > 90


def test_storyboard_validation_rejects_misleading_charts_and_unreadable_labels():
    valid = animated_scene()["visual"]
    for changes in (
        {"focus_index": 8},
        {"labels": ["8", "तेज", "9"]},
        {"labels": ["A" * 50, "B"]},
        {"kind": "bar_chart", "labels": ["A", "B"], "values": [20]},
        {"kind": "bar_chart", "labels": ["A", "B"], "values": [-3, 8]},
        {"kind": "array", "values": [1, 2]},
        {"kind": "linked_list", "labels": list("12345678")},
    ):
        with pytest.raises(ValidationError):
            VideoStoryboard.model_validate({**valid, **changes})
    with pytest.raises(ValidationError):
        VideoScene.model_validate({**animated_scene(),
                                  "code": "print('too much next to an animation')"})


def test_animated_lesson_mp4_has_measured_audio_and_safe_brand():
    scene = animated_scene("array")
    video, duration, timings = render_video(
        {"scenes": [scene]}, narrate=lambda _: b"\x10\x01" * 24000)
    assert duration == 1
    assert len(video) < 5 * 1024 * 1024
    checks = inspect_video(video, {"scenes": [scene], "timings": timings}, duration)
    assert checks["passed"] is True
    assert checks["tracks"]["video"]["frames"] == 8
    assert checks["brand_logo"]["present"] is True
    assert checks["brand_logo"]["position"] == "top-left"


def test_v4_course_requires_multiple_animated_scenes_before_narration(monkeypatch):
    from copy import deepcopy
    from app import learning_video_worker as worker
    from test_learning_video import script
    raw = script()
    for index in range(3):
        raw["scenes"][index].update(
            code="", diagram=None,
            visual=animated_scene("array")["visual"],
            bullets=["Follow the selected value"])
    checked = worker.validate_script(
        deepcopy(raw), "Evidence supporting these illustrative array indices.",
        [{"id": 1}], require_visual=True, minimum_animated=3)
    assert sum(bool(scene.visual) for scene in checked.scenes) == 3

    missing = deepcopy(raw)
    missing["scenes"][0]["visual"] = None
    monkeypatch.setattr(worker.learning_ai, "generate_json",
                        lambda *_args, **_kw: (deepcopy(missing), "isolated"))
    with pytest.raises(ValueError, match="at least three"):
        worker.validate_script(missing, "Evidence", [{"id": 1}],
                               require_visual=True, minimum_animated=3)


def test_new_courses_have_separate_animation_cache_version():
    from app.routers.learning_video import topic_key
    from hashlib import sha256
    old = sha256("shared-full-course-v3:hinglish:css".encode()).hexdigest()
    assert topic_key(" CSS ")[1] != old
    assert topic_key("css")[1] == topic_key(" CSS ")[1]

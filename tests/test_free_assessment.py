import base64
import io
import json
from fractions import Fraction
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import free_assessment, free_provider, hr_video, recording_policy
from test_hr_video import analysis, exam, seal  # noqa: F401


def transcript():
    return {"text": "Actual spoken answers", "duration": 40,
            "segments": [{"start": 0, "end": 40, "text": "Actual spoken answers", "no_speech_prob": 0.01,
                          "avg_logprob": -0.1, "compression_ratio": 1}],
            "words": [{"word": f"Answer{qid}", "start": (qid-1)*10+1, "end": (qid-1)*10+3} for qid in range(1,5)]}


def contact_sheet():
    return {
        "image": "data:image/jpeg;base64,c3ludGhldGlj",
        "panels": [
            {"question_id": 1, "panel": 1, "at_seconds": 5.0},
            {"question_id": 2, "panel": 2, "at_seconds": 15.0},
            {"question_id": 3, "panel": 3, "at_seconds": 25.0},
            {"question_id": 4, "panel": 4, "at_seconds": 35.0},
        ],
    }


def test_existing_recording_needs_new_student_processor_consent(exam, monkeypatch):
    seal(exam)
    monkeypatch.setenv("HR_AI_PROVIDER", "groq")
    monkeypatch.setattr(free_provider, "transcribe", lambda *a: pytest.fail("Unapproved recording exported"))
    with pytest.raises(HTTPException) as error:
        hr_video.analyze_recording(exam.db, exam.recording, exam.interview)
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "VIDEO_PROCESSOR_CONSENT_REQUIRED"
    with pytest.raises(HTTPException):
        recording_policy.record(exam.db, SimpleNamespace(id="intruder"), exam.interview, "groq", True)
    recording_policy.record(exam.db, exam.user, exam.interview, "groq", True)
    assert recording_policy.consented(exam.db, exam.interview)


def test_resume_preserves_transcription_vision_and_completed_questions(exam, monkeypatch):
    seal(exam)
    calls = {"transcribe": 0, "vision": 0, "grade": []}
    fail = {"value": True}

    def transcribe(*a):
        calls["transcribe"] += 1
        return transcript()

    def text(prompt, **kwargs):
        if kwargs.get("images"):
            calls["vision"] += 1
            return json.dumps({"observations": []})
        qid = json.loads(prompt[prompt.index('{'):])["question"]["question_id"]
        calls["grade"].append(qid)
        if qid == 2 and fail["value"]:
            raise free_provider.ProviderError("FREE_PROVIDER_REJECTED", 429)
        return json.dumps(analysis(exam)["answers"][qid-1])

    def persist(value):
        exam.recording.analysis_json = json.dumps(value)
        exam.db.commit()

    monkeypatch.setattr(free_provider, "transcribe", transcribe)
    monkeypatch.setattr(free_provider, "text", text)
    monkeypatch.setattr(free_assessment, "sample_contact_sheet", lambda *a: contact_sheet())

    with pytest.raises(free_provider.ProviderError):
        free_assessment.analyze(b"synthetic", exam.recording, exam.questions, persist)
    fail["value"] = False
    result = free_assessment.analyze(b"synthetic", exam.recording, exam.questions, persist)

    assert calls == {"transcribe": 1, "vision": 1, "grade": [1, 2, 2, 3, 4]}
    assert len(result["answers"]) == 4
    assert [answer["transcript"] for answer in result["answers"]] == [f"Answer{qid}" for qid in range(1,5)]
    assert all("pronunciation" in answer["feedback"] for answer in result["answers"])


def test_audio_only_coaching_discloses_that_no_visual_evidence_was_used(exam, monkeypatch):
    seal(exam)
    calls = {"grade": 0}
    monkeypatch.setattr(free_provider, "transcribe", lambda *a: transcript())
    monkeypatch.setattr(
        free_assessment,
        "sample_contact_sheet",
        lambda *a: pytest.fail("Audio-only coaching must not decode or send camera frames"),
    )

    def text(prompt, **kwargs):
        assert not kwargs.get("images")
        assert "sampled-image observations" not in prompt
        assert "No image or video evidence is available for this audio-only answer." in prompt
        payload = json.loads(prompt[prompt.index('{'):])
        assert payload["sampled_frame_observations"] == []
        qid = payload["question"]["question_id"]
        calls["grade"] += 1
        return json.dumps(analysis(exam)["answers"][qid - 1])

    monkeypatch.setattr(free_provider, "text", text)
    result = free_assessment.analyze(
        b"synthetic audio",
        exam.recording,
        exam.questions,
        lambda value: None,
        audio_only=True,
    )

    assert calls["grade"] == 4
    assert result["video_usable"] is False
    assert "No image or video evidence was used" in result["summary"]
    assert all(answer["transcript"] == f"Answer{index}" for index, answer in enumerate(result["answers"], 1))
    assert all("Speech recognition limits this coaching" in answer["feedback"] for answer in result["answers"])
    assert all("visual behavior were not assessed" in answer["feedback"] for answer in result["answers"])
    assert all("sampled images" not in answer["feedback"] for answer in result["answers"])
    assert all("Camera evidence" not in answer["feedback"] for answer in result["answers"])


def test_single_contact_sheet_distributes_valid_question_evidence(exam, monkeypatch):
    seal(exam)
    monkeypatch.setattr(free_provider, "transcribe", lambda *a: transcript())
    monkeypatch.setattr(free_assessment, "sample_contact_sheet", lambda *a: contact_sheet())
    calls = {"vision": 0}

    def text(prompt, **kwargs):
        if kwargs.get("images"):
            calls["vision"] += 1
            return json.dumps({"observations": [
                {"question_id": 1, "panel": 1, "at_seconds": 5.0, "observation": "Visible speaking posture."},
                {"question_id": 3, "panel": 3, "at_seconds": 25.0, "observation": "Visible speaking posture."},
            ]})
        payload = json.loads(prompt[prompt.index('{'):])
        qid = payload["question"]["question_id"]
        result = analysis(exam)["answers"][qid - 1]
        evidence = payload["sampled_frame_observations"]
        if qid in {1, 3}:
            assert len(evidence) == 1
            result["evidence"] = evidence
        else:
            assert evidence == []
        return json.dumps(result)

    monkeypatch.setattr(free_provider, "text", text)
    result = free_assessment.analyze(b"synthetic", exam.recording, exam.questions, lambda value: None)
    assert calls["vision"] == 1
    assert result["video_usable"] is True
    assert len(result["answers"]) == 4


def test_silence_hallucination_cannot_receive_points(exam, monkeypatch):
    seal(exam)
    noise = transcript()
    noise["segments"][0]["no_speech_prob"] = 0.99
    monkeypatch.setattr(free_provider, "transcribe", lambda *a: noise)
    monkeypatch.setattr(free_assessment, "sample_contact_sheet", lambda *a: contact_sheet())

    def text(prompt, **kwargs):
        if kwargs.get("images"):
            return json.dumps({"observations": []})
        pytest.fail("No reliable speech evidence should be graded")

    monkeypatch.setattr(free_provider, "text", text)
    result = free_assessment.analyze(b"synthetic", exam.recording, exam.questions, lambda value: None)
    assert all(answer["answer_correctness"] == 0 and answer["transcript"] == "" for answer in result["answers"])


def test_bad_camera_does_not_erase_supported_spoken_answers(exam, monkeypatch):
    seal(exam)
    monkeypatch.setattr(free_provider, "transcribe", lambda *a: transcript())
    monkeypatch.setattr(
        free_assessment,
        "sample_contact_sheet",
        lambda *a: (_ for _ in ()).throw(RuntimeError("VIDEO_PROCESSING_FAILED")),
    )

    def text(prompt, **kwargs):
        assert not kwargs.get("images")
        qid = json.loads(prompt[prompt.index('{'):])["question"]["question_id"]
        return json.dumps(analysis(exam)["answers"][qid-1])

    monkeypatch.setattr(free_provider, "text", text)
    result = free_assessment.analyze(b"synthetic", exam.recording, exam.questions, lambda value: None)
    assert result["video_usable"] is False
    assert all(answer["answer_correctness"] == 80 and "spoken answer only" in answer["feedback"] for answer in result["answers"])


def test_groq_vision_failure_is_cached_and_spoken_grading_continues(exam, monkeypatch):
    seal(exam)
    calls = {"vision": 0, "grade": 0}
    monkeypatch.setattr(free_provider, "transcribe", lambda *a: transcript())
    monkeypatch.setattr(free_assessment, "sample_contact_sheet", lambda *a: contact_sheet())

    def text(prompt, **kwargs):
        if kwargs.get("images"):
            calls["vision"] += 1
            raise free_provider.ProviderError("FREE_PROVIDER_REJECTED", 429)
        calls["grade"] += 1
        qid = json.loads(prompt[prompt.index('{'):])["question"]["question_id"]
        return json.dumps(analysis(exam)["answers"][qid - 1])

    persisted = []

    def persist(value):
        persisted.append(json.loads(json.dumps(value)))
        exam.recording.analysis_json = json.dumps(value)
        exam.db.commit()

    monkeypatch.setattr(free_provider, "text", text)
    result = free_assessment.analyze(b"synthetic", exam.recording, exam.questions, persist)

    assert result["video_usable"] is False
    assert calls == {"vision": 1, "grade": 4}
    assert all(answer["answer_correctness"] == 80 for answer in result["answers"])
    assert all("spoken answer only" in answer["feedback"] for answer in result["answers"])
    assert persisted[-1]["camera_unavailable"] is True
    assert persisted[-1]["vision_attempted"] is True
    assert persisted[-1]["observations"] == {"1": [], "2": [], "3": [], "4": []}

    # A retry must reuse cached camera-unavailable state and never retry Qwen.
    exam.recording.analysis_json = json.dumps({
        "analysis_status": "partial",
        "provider": "groq",
        "transcription": transcript(),
        "answers": [],
        "observations": persisted[-1]["observations"],
        "camera_unavailable": True,
        "vision_attempted": True,
    })
    exam.db.commit()
    again = free_assessment.analyze(b"synthetic", exam.recording, exam.questions, persist)
    assert calls["vision"] == 1
    assert len(again["answers"]) == 4


def test_contact_sheet_sparse_segments_keep_question_mapping(monkeypatch):
    class Result:
        stdout = json.dumps({
            "panels": [
                {"panel": 1, "at_seconds": 15.0},
                {"panel": 2, "at_seconds": 35.0},
            ],
            "image": "data:image/jpeg;base64,c3ludGhldGlj",
        }).encode()

    monkeypatch.setattr(free_assessment.subprocess, "run", lambda *a, **k: Result())
    segments = [
        {"question_id": 1, "start": 0, "end": 0},
        {"question_id": 2, "start": 10, "end": 20},
        {"question_id": 3, "start": 20, "end": 20},
        {"question_id": 4, "start": 30, "end": 40},
    ]
    result = free_assessment.sample_contact_sheet(b"synthetic", segments, 40)
    assert [panel["question_id"] for panel in result["panels"]] == [2, 4]
    assert [panel["at_seconds"] for panel in result["panels"]] == [15.0, 35.0]


def _synthetic_video():
    import av
    from PIL import Image

    data = io.BytesIO()
    with av.open(data, mode="w", format="webm") as container:
        stream = container.add_stream("libvpx", rate=10)
        stream.width, stream.height, stream.pix_fmt = 160, 120, "yuv420p"
        for index in range(40):
            frame = av.VideoFrame.from_image(Image.new("RGB", (160,120), "blue" if index%2 else "green"))
            frame.pts, frame.time_base = index, Fraction(1,10)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return data.getvalue()


def test_contact_sheet_decoder_handles_synthetic_video_in_isolation():
    from PIL import Image

    segments = [
        {"question_id": 1, "start": 0, "end": 1},
        {"question_id": 2, "start": 1, "end": 2},
        {"question_id": 3, "start": 2, "end": 3},
        {"question_id": 4, "start": 3, "end": 4},
    ]
    sheet = free_assessment.sample_contact_sheet(_synthetic_video(), segments, 4)
    assert [panel["question_id"] for panel in sheet["panels"]] == [1, 2, 3, 4]
    image = Image.open(io.BytesIO(base64.b64decode(sheet["image"].split(',')[1])))
    assert image.width == 512
    assert image.height == 332
    assert image.format == "JPEG"
    with pytest.raises(RuntimeError, match="VIDEO_PROCESSING_FAILED"):
        free_assessment.sample_contact_sheet(b"invalid untrusted media", segments, 4)


def test_thumbnail_decoder_handles_synthetic_video_in_isolation():
    from PIL import Image

    frames = free_assessment.sample_frames(_synthetic_video(), 0, 3)
    assert len(frames) == 3
    assert all(0 <= frame["at_seconds"] <= 3 for frame in frames)
    for frame in frames:
        image = Image.open(io.BytesIO(base64.b64decode(frame["image"].split(',')[1])))
        assert image.width == 256 and image.format == "JPEG"
    with pytest.raises(RuntimeError, match="VIDEO_PROCESSING_FAILED"):
        free_assessment.sample_frames(b"invalid untrusted media", 0, 3)

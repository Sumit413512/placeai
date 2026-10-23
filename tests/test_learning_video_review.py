import json
from copy import deepcopy

import httpx
import pytest

from test_learning_video import script
from app import learning_video_review as review


def test_audiovisual_review_requires_every_scene_and_transmits_only_teaching_media(monkeypatch):
    content = script()
    content['timings'] = [{'start': i, 'end': i+1} for i in range(4)]
    content['student_email'] = 'must-not-be-sent@example.invalid'
    result = {'approved': True, 'issues': [], 'scene_checks': [
        {'scene': i+1, 'audio_matches_script': True, 'visual_matches_audio': True} for i in range(4)]}
    monkeypatch.setattr(review.ai_provider, '_gemini_key', lambda: 'isolated-test-key')
    sent = []
    def post(url, **kwargs):
        sent.append(kwargs['json'])
        return httpx.Response(200, request=httpx.Request('POST', url), json={
            'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(result)}]}}]})
    monkeypatch.setattr(review.httpx, 'post', post)
    assert review.review_video(b'generated-test-mp4', content)['scenes_checked'] == 4
    assert 'must-not-be-sent' not in json.dumps(sent)
    assert sent[0]['contents'][0]['parts'][0]['inlineData']['mimeType'] == 'video/mp4'
    for change in ('missing', 'duplicate', 'mismatch', 'rejected', 'issues'):
        good = deepcopy(result)
        if change == 'missing': result['scene_checks'].pop()
        if change == 'duplicate': result['scene_checks'][1]['scene'] = 1
        if change == 'mismatch': result['scene_checks'][0]['audio_matches_script'] = False
        if change == 'rejected': result['approved'] = False
        if change == 'issues': result['issues'] = ['Narration does not match the diagram at 00:02']
        with pytest.raises(RuntimeError if change in {'missing', 'duplicate'} else ValueError):
            review.review_video(b'generated-test-mp4', content)
        result = good


def test_video_review_quota_pauses_instead_of_publishing_or_silently_falling_back(monkeypatch):
    content = script(); content['timings'] = []
    monkeypatch.setattr(review.ai_provider, '_gemini_key', lambda: 'isolated-test-key')
    monkeypatch.setattr(review.httpx, 'post', lambda url, **_kw: httpx.Response(
        429, request=httpx.Request('POST', url), json={'error': {'details': [{'retryDelay': '3600s'}]}}))
    with pytest.raises(review.ReviewCapacityError) as error:
        review.review_video(b'generated-test-mp4', content)
    assert error.value.retry_seconds >= 60
    monkeypatch.setattr(review.ai_provider, '_gemini_key', lambda: None)
    with pytest.raises(RuntimeError, match='VIDEO_REVIEW_UNAVAILABLE'):
        review.review_video(b'generated-test-mp4', content)

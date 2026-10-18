import io
import os

import av
import pytest


@pytest.mark.skipif(os.getenv('TEST_OFFLINE_SPEECH') != '1', reason='Optional Render-only speech runtime')
def test_real_offline_voice_encodes_a_checked_synchronized_lesson(monkeypatch):
    from app import learning_speech
    from app.learning_video_media import speak, render_video, inspect_video
    monkeypatch.setenv('LEARNING_TTS_PROVIDER','espeak')
    assert learning_speech.available()
    pcm = speak('SQL joins connect related tables. Check the join condition and inspect the resulting rows.')
    assert 24000 < len(pcm) < 24000 * 2 * 90
    scene = {'title':'Join related tables', 'narration':'SQL joins connect related tables.',
             'bullets':['Check the join condition','Inspect the resulting rows'], 'code':'', 'diagram':None}
    content = {'scenes':[scene]}
    data, duration, timings = render_video(content, narrate=lambda _text: pcm)
    content['timings'] = timings
    assert inspect_video(data, content, duration)['passed']
    with av.open(io.BytesIO(data)) as media:
        assert {s.type for s in media.streams} == {'video','audio'}
        assert abs(float(media.streams.audio[0].duration * media.streams.audio[0].time_base) - duration) < .2

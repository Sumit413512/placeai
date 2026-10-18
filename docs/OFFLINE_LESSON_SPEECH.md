# Offline lesson narration and queue recovery

Render installs `requirements-video.txt` and runs `scripts/prepare_learning_voice.py`
at build time. The downloader pins the model repository revision and SHA-256 of
both artifacts. Set `LEARNING_TTS_PROVIDER=piper` on the Render worker host.
The build converts the verified model to ORT format. Runtime inference uses the
native file loader, avoiding protobuf parsing on the 512 MB service. This uses
the same voice weights without quantization or a change to lesson content.
Vercel continues using the normal requirements; it does not synthesize narration.

Piper 1.8.0 is GPL-3.0: https://github.com/OHF-Voice/piper1-gpl
The Cori medium voice model card states that it was trained from scratch on
public-domain LibriVox recordings:
https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/en/en_GB/cori/medium/MODEL_CARD
Voice training information: https://brycebeattie.com/files/tts/

Speech runs offline in a bounded CPU subprocess with one inference thread. Native
model memory is released before video rendering. Input is stdin, never shell
code. Audio is normalized to the existing mono 24 kHz PCM contract. Playback uses
the saved MP4 and does not invoke speech again. This removes speech API charges
and quotas, but uses existing server compute; it does not make research and
independent audiovisual review unlimited or provider-independent.

There remains one heavy generation slot to protect the current small host and
assessment workload. A delayed lesson no longer pauses other due lesson jobs.
Old speech-provider waits become immediately eligible when local speech is ready.
Review waits retain unpublished rendered media and checked scripts, then resume
the same review. No unreviewed media is playable. All existing syllabus, factual,
quiz, media, audiovisual and whole-course publication gates remain mandatory.

Course notices are scoped to that course. Students see Queued, Processing, Waiting
to retry with a next retry time, or Ready to begin; preparation fractions remain
hidden. Provider review quota can still delay publication and must not be hidden
or bypassed to manufacture a ready course.

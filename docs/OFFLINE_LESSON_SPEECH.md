# Offline lesson narration and queue recovery

Render installs the pinned `espeakng-loader==0.2.4` package through
`requirements-video.txt` and verifies actual speech plus a decoded synchronized
MP4 during every build. Set `LEARNING_TTS_PROVIDER=espeak` on the worker host.
The previous `piper` setting is accepted as a rollout alias for the same offline
engine; no neural voice model is loaded. Vercel uses the normal requirements.

The loader is MIT licensed: https://github.com/thewh1teagle/espeakng-loader
The bundled eSpeak NG engine is GPL-3.0-or-later:
https://github.com/espeak-ng/espeak-ng

Narration runs in a bounded subprocess using the synchronous retrieval API,
with no playback device, SSML interpretation, network request or paid fallback.
Text enters as stdin data, never a shell command. Native callbacks enforce a
90-second scene limit. The engine uses English at 165 words per minute and
normalizes output to the existing mono 24 kHz PCM contract. The voice is more
synthetic than a neural narrator but fits the existing free server. A Linux
240 MiB address-space peak check remains required.

Audio is staged privately in a temporary file before opening video encoders,
so speech and video encoding memory peaks never overlap. Temporary data is
removed after rendering. Saved MP4 playback never invokes speech again.

One heavy generation slot protects the current host and assessment workload.
A delayed lesson no longer pauses other due jobs. Old provider waits become
eligible immediately when local speech is available, and expired admitted
leases recover regardless of their old provider cooldown. Review retries reuse
unpublished media and checked scripts. No unreviewed media is made playable.
All existing syllabus, factual, quiz, media, audiovisual and whole-course
publication gates remain required.

Course-specific notices show Queued, Processing, Waiting to retry with the next
retry time, or Ready to begin. Speech has no API charges or quota. Research and
independent audiovisual review still use provider allowances, and Render's free
compute/storage limits remain; this does not promise unlimited generation.

# Neural lesson narration and queue recovery

Render retains the pinned `espeakng-loader==0.2.4` package through
`requirements-video.txt` only for an explicit emergency/offline deployment and
verifies a decoded synchronized MP4 during every build. Production teaching uses
multilingual neural speech with `LEARNING_TTS_PROVIDER=gemini`,
`gemini-3.8-flash-tts`, and the warm `Sulafat` voice. This is required for natural
Hindi-English code switching. Vercel uses the normal requirements.

The loader is MIT licensed: https://github.com/thewh1teagle/espeakng-loader
The bundled eSpeak NG engine is GPL-3.0-or-later:
https://github.com/espeak-ng/espeak-ng

When explicitly enabled for emergency use, offline narration runs in a bounded subprocess,
with no playback device, SSML interpretation, network request or paid fallback.
Text enters as stdin data, never a shell command. Native callbacks enforce a
90-second scene limit. The emergency engine uses language-specific phonemes and
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
retry time, or Ready to begin. Neural speech, research and independent
audiovisual review use provider allowances, and Render's free
compute/storage limits remain; this does not promise unlimited generation.

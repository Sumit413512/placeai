# PlaceAI live face-to-face interview practice

This is an **optional, student-authenticated, provider-backed video conversation**. It is **not** the existing proctored 50-question assessment and does not produce an assessment score. The existing scoring and integrity flow is unchanged.

## Why this is different from a static interviewer image

The existing HR/spoken-answer assessment uses a still portrait and browser speech synthesis. The new **Meet your AI interviewer** panel connects to Tavus CVI for a real-time rendered face, audio, camera/microphone and conversational turn-taking. It is never represented as available until the provider is configured.

## Setup

1. Create a Tavus account with a consented stock face (or a properly consented custom face).
2. Configure a Tavus **PAL** to act as a professional interview coach, with live listening, role-based follow-ups, conversational voice, natural expressions and an appropriate visual-perception setting. Enable English/Hindi support in the PAL where supported and test Hinglish; the backend maps Hindi to `hindi` and Hinglish to Tavus `multilingual` for automatic language detection. The configured PAL voice/STT must still be tested for natural code-switching.
3. Set these three Vercel project **server-side** environment variables in the production and preview environments:
   - `TAVUS_API_KEY` — secret, never exposed in the browser.
   - `TAVUS_PAL_ID` — your configured PAL ID.
   - `TAVUS_FACE_ID` — a face ID approved for your account.
4. Redeploy. Sign in as a student and open `/mock-interview`. Check that the panel changes from unavailable to ready, consent to third-party processing, and start a 10-minute practice.
5. Test camera/microphone permissions on Chrome, Safari and mobile; test natural pauses, interruption, role follow-ups, room teardown, Hindi/Hinglish speech, captions, bandwidth loss and accessibility. Verify vendor billing and data-retention controls before making this available to students at scale.

## Security and limitations

- All Tavus API calls are server-side. Only a short-lived private meeting URL and a user-bound, HMAC-signed end-session proof reach the browser.
- The session requires student authentication, active preparation entitlement, AI request throttling (two live starts per student per hour) and explicit per-call consent.
- Sessions are capped at 10 minutes, with a 30-second participant-left timeout. The browser attempts an authenticated end call on normal exit. Unexpected network disconnects may take longer to terminate.
- Camera, microphone and conversation are handled by the video provider; PlaceAI does not save a recording or generate a score for this feature. Configure Tavus retention, recordings and perception appropriately and update institutional data-processing agreements before wide release.
- Do not use gaze or inferred emotion as a hiring score. The AI avatar's apparent eye contact and expression quality depend on the provider's chosen face/PAL.
- If credentials are missing or the provider is down, the panel says unavailable; the existing scored assessment remains usable.
- Vendor usage incurs cost. Do not enable at scale without quotas, billing alerts, a per-user concurrent-session cap and an explicit institutional privacy review.

## Provider docs

- https://docs.tavus.io/api-reference/conversations/create-conversation
- https://docs.tavus.io/api-reference/conversations/end-conversation

## PAL quality configuration and acceptance tests

Configure the Tavus PAL with a **consented, camera-facing professional face**, a clear, warm, human-sounding voice, natural conversational turn-taking, and optional visual perception. The selected face should look toward the camera while speaking. The backend provides per-session interview instructions, but the PAL's own voice, visual-perception, speech-recognition and conversational-flow settings control the actual live quality.

**Suggested PAL system behavior**: Act as an attentive, respectful mock interviewer. Ask a single concise question, listen to the full answer, acknowledge a concrete detail, then ask a relevant follow-up. Use short natural pauses, don't lecture or interrupt, and let the student ask for clarification. When discussing programming, use technical terms accurately. For Hinglish, keep technical terms in English and use natural Hindi-English code switching. Provide constructive verbal feedback at the end. Never pretend to be a human interviewer or a real employer. Never infer personality, emotion or hiring suitability from the student's face, gaze or surroundings.

**Acceptance checklist before production**:
- Confirm the provider actually shows a **moving, speaking avatar**, not a static image, on desktop and mobile.
- Ask a question, answer partially, and confirm the next question **references that answer**.
- Interrupt the interviewer and confirm turn-taking behaves naturally without talking over the student.
- Test English, Hindi and Hinglish with real voices, including technical vocabulary and realistic pauses.
- Verify lip-sync, camera-facing gaze, latency, audio echo cancellation, captions, poor network recovery, and denied camera/microphone permissions.
- Confirm a denied permission prompt does **not** create a billable Tavus conversation.
- Verify the 10-minute server-side cap, automatic cleanup, two starts per student per hour, no recording, and the student-facing third-party privacy disclosure.
- Verify the existing scored/proctored assessment remains unchanged, and do not enable this provider for high-stakes hiring judgments.

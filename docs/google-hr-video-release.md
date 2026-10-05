# Google sign-in and recorded HR assessment

Google sign-in verifies Google's signed ID token and a signed, short-lived browser
challenge. Existing roles and institution membership are preserved. Google cannot
create an institution or platform administrator. Non-Gmail/non-Workspace accounts
must confirm their existing PlaceAI password before the first account link.

Production Google Cloud project: `placeai-510510`.
Web client: `PlaceAI production sign-in`.
Authorized origin: `https://www.placeai.in`.
Set `GOOGLE_CLIENT_ID` to the public client ID from that project. No client secret
is needed for this Google Identity Services ID-token flow. Configure external
production audience and verify the real Google button before announcing availability.

The proctored assessment starts its server clock after device checks. Four HR
questions use one continuous camera/microphone recording, up to 150 seconds per
question. Uploads are sequential, idempotent and bounded. The complete recording
is sealed before analysis; all answers are saved before contacting Gemini. Every
section's result stays withheld until all required grading succeeds. Students can
retry saved analysis from their history without changing submitted answers.

Explicit student consent covers the camera, voice and answers sent to Gemini.
The coaching rubric assesses answer correctness, clarity and English fluency;
it must not infer personality, emotion, honesty, protected traits or employability.
Timestamped observations link to the private recording. These are practice results
for human review, not automated hiring or misconduct decisions.

## Release order

1. Require PlaceAI CI and PlaceAI Security Audit to pass on the exact PR head.
2. Apply Alembic revision `20261003_0015` before the application release. The three
   new tables are private to the server: enable RLS and revoke anon/authenticated
   access; PlaceAI's own account and tenant checks authorize all endpoints.
3. Apply `scripts/hr_recording_retention.sql` on PlaceAI Supabase. Confirm the
   named cron job is active. Playback/upload access ends at 30 days; the hourly
   job purges expired recording bytes in bounded batches. Reports remain.
4. Set the Google client ID in Vercel production and deploy the green commit.
5. Verify actual Google login, one isolated roadmap with sources, and a consented
   synthetic HR recording through final combined results. Confirm Gemini quota
   is available. Unit/browser fixtures do not prove external provider availability.
6. Remove the disposable account and related data using exact account ownership
   checks after retaining non-sensitive diagnostic evidence.

Gemini uploaded files are reused while processing. PlaceAI requests deletion after
analysis; failed deletion relies on Google's Files API expiry (48 hours). A failed
provider request never produces a fabricated score. The signed-in user must keep
the exam tab open until uploads finish; already submitted attempts are recoverable.

Sources: [Google Identity Services setup](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid),
[Gemini video](https://ai.google.dev/gemini-api/docs/video-understanding),
[Gemini file retention](https://ai.google.dev/gemini-api/docs/files),
[Supabase Cron](https://supabase.com/docs/guides/cron/install).

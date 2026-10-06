# PlaceAI no-billing pilot — 6 October 2026

## Proposed route

Keep the existing deployment and objective/coding grading. Add an explicitly selected Groq free-tier provider for text analysis, Whisper transcription and Qwen image observations. Do not repurpose a consumer subscription, cycle accounts/API keys to evade quotas, enable billing, or silently use a paid fallback. Groq approval and a server-side free-plan API key are required before activation. The new adapter is prepared locally, not activated or production-verified.

## Feature coverage and limits

| Feature | Approach | Required verification |
| --- | --- | --- |
| Technical MCQ results | Existing answer keys | No AI API needed |
| Coding results | Existing isolated execution and test cases | Preserve execution admission and security |
| Descriptive feedback | GPT-OSS 120B on Groq | Issued-question rubric, structured output, irrelevant-answer gate and complete question coverage |
| Spoken answers | Whisper large-v3 with segment timestamps | Check silence/hallucination metadata and answer alignment; do not infer pronunciation or continuous-video behavior from a transcript |
| HR camera evidence | Qwen 3.8 27B can accept up to three images per request | Sampled-image observations are not full-video understanding; directly visible events only, no inferred personality/emotion/honesty or hiring decisions |
| Career Roadmap research | Explicit live public-job-feed mode | Minimum matched sources and skill signals remain mandatory; disclose the sample and fail safely if evidence is insufficient |
| Delayed reports | Saved answers plus bounded queued recovery | Reviewed queue runtime access and worker admission still required; provider limits cannot be fixed by waiting forever |

## No-billing controls

1. Verify the actual Groq organization is Free, without an active paid plan. Do not add a card or payment method.
2. Enable Zero Data Retention in that organization and verify the applied setting before sending student data. Obtain approval of Groq as the processor and update student consent. Existing Google/OpenAI approvals do not establish Groq approval.
3. Store `GROQ_API_KEY` only in server deployment settings; never in source, public JavaScript, chat or logs.
4. `GROQ_PROCESSING_APPROVED=true`, `TEXT_AI_PROVIDER=groq`, `HR_AI_PROVIDER=groq` and `VISION_AI_PROVIDER=groq` are explicit activation controls. `ROADMAP_RESEARCH_PROVIDER=public` uses fresh public job evidence without an AI API. Defaults preserve the existing provider configuration. Do not activate recording/vision routes until their end-to-end evidence checks pass.
5. Keep one fixed API destination, bounded responses, no redirects and no immediate quota retries. Preserve submissions when quota is exhausted. A missing/free quota must not cause automatic paid fallback.
6. Limit this rollout to a small pilot. The published free limits currently list 28,800 audio seconds per day for Whisper and 200,000 tokens per day for GPT-OSS 120B; hourly/minute limits also apply. Account limits can differ and must be inspected. Ten-minute HR audio alone would allow at most 48 attempts/day under that audio cap, before other spoken answers, retries, or hourly limits. This is a theoretical quota calculation, not a throughput or availability guarantee.
7. Retain on-device background proctoring in the pilot. Disable frequent secondary cloud frame checks so they cannot exhaust the quota needed for HR feedback. Sampled-frame feedback remains labelled; camera decoding failure does not erase supported spoken answers or invent camera observations.
8. Existing pending recordings require a new student consent event before Groq processing. Per-question analyses, transcription and frame observations are saved privately between retries; complete scores remain hidden until the entire exam is evaluated.

## Subscription findings

Google AI Pro lists consumer/developer product benefits but does not establish Gemini API quota for the production project; API billing and limits are separate. ChatGPT plan usage is available in eligible participating apps with per-user authorization, not a general website API allowance obtained from one owner's subscription. PlaceAI app approval has not been established. No subscription tokens or browser automation will be used as a production inference backend.

Sources: [Groq data controls](https://console.groq.com/docs/your-data), [Groq limits](https://console.groq.com/docs/rate-limits), [Groq billing](https://console.groq.com/docs/billing-faqs), [speech transcription](https://console.groq.com/docs/speech-to-text), [strict output](https://console.groq.com/docs/structured-outputs), [image capabilities](https://console.groq.com/docs/vision), [Google AI Pro benefits](https://support.google.com/googleone/answer/14534406), [Gemini API billing](https://ai.google.dev/gemini-api/docs/billing), [ChatGPT plan integration](https://developers.openai.com/siwc/quickstart).

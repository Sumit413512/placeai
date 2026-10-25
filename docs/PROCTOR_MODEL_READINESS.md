# Proctor detector readiness and recovery

## Problem
TechNova and Zensar share the same secure assessment preflight. The former loader depended on external JavaScript/model downloads and an unbounded initialization promise; a stalled initialization could leave Loading model visible indefinitely, including on retry.

## Change
- Pin and serve TensorFlow.js 4.22.0, its matching ES2017 WebAssembly backend, COCO-SSD 2.2.3 and lite model weights from the application origin. Asset provenance and SHA-256 values are in ASSETS.json; upstream licenses are retained.
- Prepare and warm up the real detector in a dedicated worker before device checks, in parallel with assessment preparation. WebAssembly uses one thread, without cross-origin-isolation requirements. Camera access is not needed to prepare the detector.
- Publish Ready only after actual inference succeeds. Bound initial preparation to 45 seconds and each inference to 10 seconds; terminate stalled workers and make retry create a fresh worker.
- Invalidate readiness after detector failure. Reset liveness after a device recheck. Prevent concurrent device checks.
- Restrict the WebAssembly CSP allowance to the same-origin worker. Page JavaScript evaluation remains blocked. Media consent, screen sharing, liveness, fullscreen, scoring and exam timing remain required and unchanged.
- Cache versioned immutable detector assets on both deployments. Mirrors and every model shard are checked by tests. No paid hosting or provider is introduced.

## Verification scope
Real browser tests load the actual model and run inference against a blank canvas. Failure and timeout tests verify independent retry and blocked exam entry. Media workflow tests use synthetic inputs rather than the operator camera or microphone. Isolated accounts cover student, recruiter, institution and platform navigation, responsive layouts, notes/PDF, video/quiz progress, study tracking, authentication handoff, resume evidence and document permissions. These tests do not prove production third-party AI quota availability or every real device/browser combination.

Local model warmup plus inference was approximately two seconds on the test machine; this is a measurement, not a promised download time. Slow first downloads can require retry. Both hosting delivery paths must be checked after deployment for asset availability and worker CSP.

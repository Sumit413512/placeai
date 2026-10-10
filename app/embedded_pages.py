from __future__ import annotations

# Vercel's Python runtime traces imported Python modules reliably, while non-Python
# template files can be omitted from a serverless function bundle. These copies are
# intentional last-resort fallbacks; the canonical editable templates remain under
# app/templates and are preferred whenever they are available at runtime.

INDEX_HTML = '''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="PlaceAI is an AI-assisted campus placement operating system for institutions, recruiters, and students.">
  <meta name="theme-color" content="#59416f">
  <title>PlaceAI — Campus placement operations</title>
  <link rel="icon" type="image/svg+xml" href="/static/placeai-icon.svg">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/static/app.css">
  <link rel="stylesheet" href="/static/brand.css">
<link rel="canonical" href="https://www.placeai.in/">
<meta property="og:type" content="website">
<meta property="og:site_name" content="PlaceAI">
<meta property="og:title" content="PlaceAI — Campus placement operations">
<meta property="og:description" content="PlaceAI is an AI-assisted campus placement operating system for institutions, recruiters, and students.">
<meta property="og:url" content="https://www.placeai.in/">
<meta property="og:image" content="https://www.placeai.in/static/placeai-hero-approved-hd.webp">
<meta property="og:image:alt" content="PlaceAI campus placement collaboration">
<meta name="twitter:card" content="summary_large_image">
<link rel="stylesheet" href="/static/privacy-preferences.css"><script src="/static/privacy-preferences.js" defer></script>
<link rel="stylesheet" href="/static/selected-theme.css?v=20261010-readability">
</head>
<body>
  <div id="toast-region" class="toast-region" aria-live="polite"></div>

  <div id="marketing-site">
    <header class="site-header">
      <a class="brand" href="#top" aria-label="PlaceAI home">
        <span class="brand-mark" aria-hidden="true"><span></span><span></span><span></span></span>
        <span>PlaceAI</span>
      </a>
      <nav class="marketing-nav" aria-label="Primary navigation">
        <a href="#platform">Platform</a>
        <a href="#institutions">Institutions</a>
        <a href="#recruiters">Recruiters</a>
        <a href="#preparation-lab">Preparation Lab</a>
        <a href="#security">Security</a>
      </nav>
      <div class="header-actions">
        <button class="button button-ghost" data-open-auth="login">Sign in</button>
        <button class="button button-primary" data-open-access="request">Request access</button>
      </div>
      <button class="mobile-menu" data-action="toggle-mobile-menu" aria-label="Open navigation">Menu</button>
    </header>

    <main id="top">
      <section class="hero section-shell">
        <div class="hero-copy">
          <div class="eyebrow"><span class="eyebrow-dot"></span> Campus placement operations for institutions, recruiters and students</div>
          <h1>Placement operations,<br><span>connected end to end.</span></h1>
          <p class="hero-journey-line">Learn · Practice · Get Placed</p>
          <p class="hero-lead">Build skills with AI-guided learning, practice with prompt-led mock interviews, and connect your preparation to campus hiring — all in one PlaceAI workspace.</p>
          <div class="hero-actions">
            <button class="button button-primary button-large" data-open-auth="login">Sign in to PlaceAI</button>
            <button class="button button-secondary button-large" data-open-access="request">Request workspace access</button>
          </div>
          <div class="hero-trust">
            <div><strong>Role-based access</strong><span>Student, recruiter, institution and platform controls</span></div>
            <div><strong>Production data only</strong><span>Operational records come from authenticated workspace activity</span></div>
            <div><strong>Human-reviewed AI</strong><span>Decision support remains subject to authorized human review</span></div>
          </div>
        </div>

        <div class="hero-product" aria-label="PlaceAI production workspace information">
          <figure class="hero-photo-card">
            <img src="/static/placeai-hero-approved-hd.webp" alt="Illustrative student collaboration scene for the PlaceAI placement journey" loading="eager" fetchpriority="high" decoding="async" width="1672" height="941">
            <figcaption><span>From preparation to placement</span><strong>One connected campus journey.</strong></figcaption>
          </figure>
          <div class="production-surface-card hero-surface-card">
            <div>
              <span class="surface-kicker">Your placement journey</span>
              <h3>Preparation and campus hiring, working together.</h3>
              <p>A shared workspace for students, placement teams and recruiters, with the right access at every stage.</p>
            </div>
            <div class="production-surface-grid">
              <div><strong>Student</strong><span>Profile, eligibility, applications, documents and interview preparation.</span></div>
              <div><strong>Recruiter</strong><span>Approved jobs, applicant pipelines, interviews, offers and company verification.</span></div>
              <div><strong>Institution Admin</strong><span>Students, recruiters, drives, approvals, attendance, governance and reports.</span></div>
              <div><strong>Platform Admin</strong><span>Institution setup, access review and platform operations.</span></div>
            </div>
          </div>
        </div>
      </section>

      <section class="learning-journey section-shell" aria-labelledby="learning-journey-title">
        <div class="journey-heading"><span class="section-kicker">From learning to opportunity</span><h2 id="learning-journey-title">A clear path forward.</h2></div>
        <ol class="journey-grid">
          <li class="journey-card"><span class="journey-index" aria-hidden="true">01</span><h3>Learn</h3><p>Turn AI-guided explanations into useful study notes, and build a practical career roadmap around your target role.</p><a href="#preparation-lab">Explore guided learning <span aria-hidden="true">→</span></a></li>
          <li class="journey-card"><span class="journey-index" aria-hidden="true">02</span><h3>Practice</h3><p>Prepare with prompt-led mock interviews, timed assessments and feedback that helps you improve your next answer.</p><a href="#preparation-lab">Explore interview practice <span aria-hidden="true">→</span></a></li>
          <li class="journey-card"><span class="journey-index" aria-hidden="true">03</span><h3>Get Placed</h3><p>Connect your readiness to campus opportunities, applications and interviews coordinated by placement teams and recruiters.</p><a href="#institutions">Explore campus hiring <span aria-hidden="true">→</span></a></li>
        </ol>
      </section>

      <section class="proof-strip">
        <div class="section-shell proof-content">
          <span>Designed to replace fragmented placement operations across</span>
          <strong>Spreadsheets</strong><i></i><strong>Messaging threads</strong><i></i><strong>Scattered resumes</strong><i></i><strong>Manual reports</strong>
        </div>
      </section>

      <section id="platform" class="section-shell value-section">
        <div class="section-heading">
          <div><span class="section-kicker">One operating layer</span><h2>Every placement workflow,<br>connected to the same record.</h2></div>
          <p>PlaceAI gives each stakeholder a purpose-built workspace while preserving institution boundaries, auditability and controlled access.</p>
        </div>
        <div class="feature-bento">
          <article class="bento-card bento-large"><span class="card-number">01</span><div><h3>Placement command centre</h3><p>Track students, eligibility, active drives, applications, interviews, offers and outcomes from production records instead of manually assembled summaries.</p></div></article>
          <article class="bento-card"><span class="card-number">02</span><h3>Eligibility enforcement</h3><p>Institutions configure academic and batch requirements. Students receive eligibility results from their stored profile and the actual drive criteria.</p></article>
          <article class="bento-card"><span class="card-number">03</span><h3>Recruiter pipeline</h3><p>Recruiters work only with authorized jobs and candidate pipelines, with status movement recorded against real applications.</p></article>
          <article class="bento-card bento-wide"><span class="card-number">04</span><div><h3>Student readiness</h3><p>Profile completion, resume records, documents, interview preparation and application history are tied to the signed-in student account.</p></div></article>
        </div>
      </section>

      <section id="preparation-lab" class="section-shell preparation-section">
        <div class="section-heading compact preparation-heading">
          <div><span class="section-kicker">Preparation Lab</span><h2>Student preparation, connected to placement.</h2></div>
          <p>Bring readiness, resume records, interview preparation and application context into the same authenticated student workspace.</p>
        </div>
        <div class="preparation-grid">
          <article><span>01</span><h3>Profile readiness</h3><p>Keep academic details, skills and placement preferences connected to the signed-in student account.</p></article>
          <article><span>02</span><h3>Resume intelligence</h3><p>Use structured resume records and AI-assisted analysis without replacing authorized human review.</p></article>
          <article><span>03</span><h3>Interview practice</h3><p>Prepare with role-grounded mock interview workflows linked to the student's placement context.</p></article>
          <article><span>04</span><h3>Opportunity context</h3><p>Move from preparation into eligible opportunities, applications and placement activity in one platform.</p></article>
        </div>
      </section>

      <section id="institutions" class="dark-section">
        <div class="section-shell dark-grid">
          <div class="dark-copy">
            <span class="section-kicker light">For placement teams</span>
            <h2>Operate placement workflows with institutional control.</h2>
            <p>Add approved users, verify student records, review campus jobs, configure drives, manage attendance and export placement data while keeping candidate information private.</p>
            <ul class="check-list">
              <li>Institution-scoped student records and verification</li>
              <li>Approved recruiter onboarding and campus-job approval</li>
              <li>Drive eligibility by configured academic criteria</li>
              <li>Application, interview, offer and placement outcome tracking</li>
              <li>Audit, policy, incident and reporting workflows</li>
            </ul>
            <button class="button button-light button-large" data-open-access="request">Request institution access</button>
          </div>
          <div class="production-surface-card">
            <div><span class="surface-kicker">Institution controls</span><h3>Institution data stays separated by design.</h3><p>Each placement team works only with the students, recruiters, jobs and placement records authorized for its institution.</p></div>
          </div>
        </div>
      </section>

      <section id="recruiters" class="section-shell role-section">
        <div class="section-heading compact">
          <div><span class="section-kicker">For hiring teams</span><h2>Campus hiring,<br>clearly coordinated.</h2></div>
          <p>Recruiter workspaces use real company profiles, approved opportunities and actual applicants. Candidate access follows the placement pipeline and institution controls.</p>
        </div>
        <div class="role-production">
          <div class="production-surface-card">
            <div><span class="surface-kicker">Controlled recruiter access</span><h3>Applicant data appears only when real candidates enter an authorized pipeline.</h3><p>Recruiter views do not use sample identities or fabricated match scores. AI-assisted analysis is generated only from authorized production inputs and remains human-reviewed.</p></div>
            <div class="production-surface-grid"><div><strong>Company verification</strong><span>Evidence and institution-linked trust review.</span></div><div><strong>Application pipeline</strong><span>Actual status movement from application through final outcome.</span></div></div>
          </div>
        </div>
      </section>

      <section id="security" class="section-shell security-section">
        <div class="security-card">
          <span class="security-orbit"></span>
          <div><span class="section-kicker">Built for institutional trust</span><h2>Candidate data stays behind authenticated, role-aware controls.</h2><p>PlaceAI defaults to controlled access. Public visitors cannot browse student records, recruiter pipelines or institution operations.</p></div>
          <div class="security-grid">
            <div><strong>Verified workspace access</strong><span>PlaceAI opens the workspace assigned to each approved account.</span></div>
            <div><strong>Institution data boundaries</strong><span>Student and campus information stays within authorized institution access.</span></div>
            <div><strong>Secure account recovery</strong><span>Password reset uses a time-limited link without revealing whether an account exists.</span></div>
            <div><strong>Reliable AI behavior</strong><span>If AI is unavailable, core workflows stay usable instead of showing invented analysis.</span></div>
          </div>
        </div>
      </section>

      <section class="cta-section"><div class="section-shell cta-inner"><div><span>Need a PlaceAI workspace?</span><h2>Choose the correct role<br>and request controlled access.</h2></div><button class="button button-light button-large" data-open-access="request">Request access</button></div></section>
    </main>

    <footer class="site-footer section-shell"><a class="brand" href="#top"><span class="brand-mark"><span></span><span></span><span></span></span><span>PlaceAI</span></a><p>AI-assisted campus placement operating system.</p><span>© 2026 PlaceAI · Privacy-first campus hiring.</span></footer>
  </div>

  <div id="app-shell" class="app-shell hidden">
    <aside class="app-sidebar">
      <div class="sidebar-brand"><a class="brand brand-light" href="#"><span class="brand-mark"><span></span><span></span><span></span></span><span>PlaceAI</span></a><button class="sidebar-close" data-action="toggle-sidebar" aria-label="Close sidebar">×</button></div>
      <div class="workspace-pill"><span class="workspace-avatar" id="workspace-avatar">P</span><div><small id="workspace-kind">Workspace</small><strong id="workspace-name">PlaceAI</strong></div></div>
      <nav id="app-nav" class="app-nav" aria-label="Workspace"></nav>
      <div class="sidebar-bottom"><div class="ai-policy"><span>AI</span><p><strong>Human-reviewed intelligence</strong><small>AI features support—not replace—placement decisions.</small></p></div><button class="sidebar-user" data-action="logout"><span class="user-avatar" id="sidebar-avatar">U</span><span><strong id="sidebar-user-name">Account</strong><small id="sidebar-user-role">Role</small></span><em>Sign out</em></button></div>
    </aside>
    <button class="sidebar-backdrop" id="sidebar-backdrop" type="button" data-action="toggle-sidebar" aria-label="Close navigation"></button>
    <div class="app-content-wrap">
      <header class="app-topbar"><button class="sidebar-trigger" data-action="toggle-sidebar">Menu</button><div class="topbar-context"><small id="page-eyebrow">Workspace</small><strong id="page-title">Dashboard</strong></div><div class="topbar-actions"><button class="icon-button command-launch" data-action="open-command-palette" title="Search PlaceAI" aria-label="Search PlaceAI"><span class="command-launch-icon">⌕</span>Search <kbd>Ctrl K</kbd></button><button class="icon-button" id="notifications-button" data-action="open-notifications" title="Notifications" aria-label="Notifications"><span class="notification-dot"></span>Updates <b id="notification-count" class="notification-count">0</b></button><button class="button button-primary button-small" id="context-action">New</button></div></header>
      <main id="app-content" class="app-content"><div class="loading-state"><span class="loader"></span><p>Loading your workspace…</p></div></main>
    </div>
  </div>

  <div id="auth-overlay" class="modal-overlay hidden" role="dialog" aria-modal="true" aria-labelledby="auth-title" tabindex="-1">
    <div class="auth-modal">
      <button class="modal-close" data-action="close-auth" aria-label="Close">×</button>
      <div class="auth-brand-panel"><a class="brand brand-light" href="#"><span class="brand-mark"><span></span><span></span><span></span></span><span>PlaceAI</span></a><div><span class="auth-panel-kicker">Secure access</span><h2>Sign in to the workspace assigned to you.</h2><p>Choose the role provided with your PlaceAI account. Admin access is limited to approved accounts.</p></div><div class="auth-proof"><span>Verified roles</span><span>Institution data boundaries</span><span>Privacy-first candidate access</span></div></div>
      <div class="auth-form-panel">
        <div id="login-view"><span class="section-kicker">Secure access</span><h2 id="auth-title">Sign in to PlaceAI</h2></div>
        <div id="signup-view" class="hidden"><span class="section-kicker">Account access</span><h2 id="auth-create-title">Create or request access</h2></div>
        <div id="reset-view" class="hidden"><span class="section-kicker">Account recovery</span><h2 id="auth-reset-title">Reset your password</h2><p class="form-intro">Enter your email to request a one-time reset link. For privacy, PlaceAI shows the same confirmation whether or not an account exists.</p><form id="forgot-form" class="form-stack"><label>Email address<input type="email" name="email" required autocomplete="email"></label><button class="button button-primary button-full">Send reset link</button></form><button class="text-button back-link" data-action="show-login">← Back to sign in</button></div>
      </div>
    </div>
  </div>

  <div id="generic-modal" class="modal-overlay hidden" role="dialog" aria-modal="true" aria-label="Dialog" tabindex="-1">
    <div class="generic-modal-card">
      <button class="modal-close" data-action="close-generic-modal" aria-label="Close dialog">×</button>
      <div id="generic-modal-content" class="generic-modal-content"></div>
      <div class="generic-modal-actions"><button id="generic-modal-cancel" class="button button-secondary" type="button" data-action="close-generic-modal">Cancel</button></div>
    </div>
  </div>

  <div id="command-palette" class="command-palette hidden" role="dialog" aria-modal="true" aria-labelledby="command-title">
    <button class="command-backdrop" data-action="close-command-palette" aria-label="Close search"></button>
    <section class="command-card">
      <div class="command-input-row"><span>⌕</span><input id="command-search" type="search" autocomplete="off" placeholder="Search students, companies, jobs, drives…" aria-label="Search PlaceAI"><kbd>Esc</kbd></div>
      <div class="command-meta"><strong id="command-title">Quick search</strong><span>Jump directly to authorized records and workspaces</span></div>
      <div id="command-results" class="command-results"><div class="command-hint">Type at least two characters to search your authorized PlaceAI data.</div></div>
    </section>
  </div>

  <script src="/static/app.js" defer></script>
</body>
</html>
'''

PRIVACY_HTML = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="PlaceAI Privacy Policy"><title>Privacy Policy — PlaceAI</title><link rel="icon" type="image/svg+xml" href="/static/placeai-icon.svg"><link rel="stylesheet" href="/static/legal.css"><link rel="canonical" href="https://www.placeai.in/privacy">
<meta property="og:type" content="website">
<meta property="og:site_name" content="PlaceAI">
<meta property="og:title" content="Privacy Policy — PlaceAI">
<meta property="og:description" content="PlaceAI Privacy Policy">
<meta property="og:url" content="https://www.placeai.in/privacy">
<meta property="og:image" content="https://www.placeai.in/static/placeai-hero-approved-hd.webp">
<meta property="og:image:alt" content="PlaceAI campus placement collaboration">
<meta name="twitter:card" content="summary_large_image">
<link rel="stylesheet" href="/static/selected-theme.css?v=20261010-readability">
</head><body><div class="legal-shell"><header class="legal-top"><a class="legal-brand" href="/">PlaceAI</a><nav class="legal-nav" aria-label="Legal"><a href="/privacy">Privacy</a><a href="/terms">Terms</a><a href="/acceptable-use">Acceptable Use</a><a href="/">Back to PlaceAI</a></nav></header><section class="legal-hero"><span class="legal-kicker">Legal & privacy</span><h1>Privacy Policy</h1><p>This policy explains how PlaceAI handles personal and institutional information when providing campus placement operations, applicant workflows, recruiter tools and AI-assisted features.</p><div class="legal-meta">Effective: 6 October 2026</div></section><main class="legal-card"><div class="legal-note">PlaceAI is designed for controlled institutional use. Institution-specific contractual or data-processing terms may provide additional protections and take precedence where applicable.</div><h2>1. Information we process</h2><p>Depending on your role and the features your institution enables, PlaceAI may process account and identity information; academic and student profile information; resumes and supporting documents; job applications, eligibility results, interviews, attendance and offers; recruiter and company verification information; communications, audit events and security logs; and technical information necessary to operate and secure the service.</p><h2>2. Why we process information</h2><p>We use information to authenticate users, provide role-based placement workflows, manage institution and recruiter operations, evaluate configured eligibility criteria, support interview and application workflows, send account and security communications, prevent abuse, maintain auditability, diagnose service issues and provide authorized AI-assisted analysis.</p><h2>3. Institutions and authorized users</h2><p>For institution-managed records, the relevant institution may determine why and how student or placement information is used. PlaceAI processes that information to provide the service and according to the institution's authorized configuration, applicable agreements and law. Users must only access information they are authorized to handle.</p><h2>4. AI-assisted features</h2><p>PlaceAI sends the minimum information necessary for a requested AI feature to its configured providers: OpenAI, Google Gemini or, when the free pilot is enabled, Groq. Provider availability depends on the feature and configuration. AI output is practice coaching or decision support for authorized human review, and is not a guaranteed hiring, placement or eligibility decision. Public-market roadmap evidence may be collected from public job feeds without an AI API.</p><h3>Recorded spoken answers</h3><p>With explicit consent, descriptive answers can be recorded separately as voice and HR answers as camera-and-microphone clips. Legacy assessments may contain a single HR video. The assessment notice identifies the configured processor before recording. Switching an existing recording to Groq requires the student's updated consent. Groq processing is enabled only after its Zero Data Retention setting is verified; audio/video files are submitted for transcription, and selected video frames may be analyzed for directly visible communication observations. Speech recognition and sampled frames do not establish pronunciation accuracy, continuous-video behavior, personality, emotion, honesty or employment suitability.</p><p>The student and authorized staff in the same institution may review private recordings for 30 days. Scheduled cleanup removes expired recording bytes while reports and feedback may remain. For Gemini processing, PlaceAI requests deletion of the uploaded provider copy after analysis; the Files API also expires uploads after 48 hours. For Groq processing, inference requests use Zero Data Retention rather than persistent remote file storage. Quota limits can delay analysis; complete results appear together after every required question has been evaluated. Recordings and submitted answers are preserved while analysis is pending, subject to retention expiry.</p><h2>5. Service providers and international processing</h2><p>PlaceAI uses infrastructure and communications providers to host the application, database, transactional email and AI functionality. These providers may process information in jurisdictions outside the user's location. PlaceAI limits provider access to what is necessary to deliver and secure the service.</p><h2>6. Cookies and session information</h2><p>PlaceAI uses essential authentication and security mechanisms required to sign users in, maintain authorized sessions and protect accounts. PlaceAI does not require advertising cookies to operate the placement workspace.</p><p>If you choose Google sign-in, PlaceAI receives a verified Google account identifier, email and name to authenticate and link your account. Google sign-in does not grant PlaceAI access to Gmail messages or Drive files and does not change your assigned role.</p><p>Optional first-party page-usage analytics run only after you choose to allow them in Privacy choices. You can decline or withdraw permission at any time using the Privacy choices control. We respect browser Do Not Track and Global Privacy Control signals. Analytics use random identifiers stored as keyed hashes and omit assessment answers, recordings, passwords, full referral URLs and page query strings. Essential sign-in and security cookies continue to work when analytics are declined.</p><h2>7. Retention</h2><p>Information is retained for as long as required to provide the service, satisfy institutional instructions, preserve legitimate security and audit records, meet contractual obligations or comply with applicable law. Retention requirements may vary by institution and record type.</p><h2>8. Security</h2><p>PlaceAI uses role-based authorization, institution scoping, encrypted HTTPS transport, secure password handling, session controls, audit records, rate limiting, security headers, dependency scanning and production health checks. No online service can guarantee absolute security, so suspected security incidents should be reported promptly through the authorized PlaceAI support channel.</p><h2>9. Your choices and rights</h2><p>Users may request access, correction or other action concerning personal information through their institution where the institution manages that information, or through the PlaceAI support/access channel for platform-managed information. Requests are handled subject to identity verification, institutional responsibilities and applicable law.</p><h2>10. Student and age considerations</h2><p>PlaceAI is intended primarily for higher-education placement operations. Institutions are responsible for ensuring that accounts and student information are collected and used with the appropriate authority, notice or consent required by applicable law.</p><h2>11. Changes to this policy</h2><p>We may update this policy when the service, providers, legal requirements or data practices change. The effective date above will be updated when material revisions are published.</p><h2>12. Contact</h2><p>For privacy or data-handling questions, use the PlaceAI access/support channel or the support contact supplied by your institution. Security vulnerabilities should be reported through the process described in PlaceAI's Security Policy.</p></main><footer class="legal-footer"><span>© 2026 PlaceAI</span><span><a href="/terms">Terms</a> · <a href="/acceptable-use">Acceptable Use</a></span></footer></div></body></html>'''

TERMS_HTML = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="PlaceAI Terms of Use"><title>Terms of Use — PlaceAI</title><link rel="icon" type="image/svg+xml" href="/static/placeai-icon.svg"><link rel="stylesheet" href="/static/legal.css"><link rel="canonical" href="https://www.placeai.in/terms">
<meta property="og:type" content="website">
<meta property="og:site_name" content="PlaceAI">
<meta property="og:title" content="Terms of Use — PlaceAI">
<meta property="og:description" content="PlaceAI Terms of Use">
<meta property="og:url" content="https://www.placeai.in/terms">
<meta property="og:image" content="https://www.placeai.in/static/placeai-hero-approved-hd.webp">
<meta property="og:image:alt" content="PlaceAI campus placement collaboration">
<meta name="twitter:card" content="summary_large_image">
<link rel="stylesheet" href="/static/selected-theme.css?v=20261010-readability">
</head><body><div class="legal-shell"><header class="legal-top"><a class="legal-brand" href="/">PlaceAI</a><nav class="legal-nav" aria-label="Legal"><a href="/privacy">Privacy</a><a href="/terms">Terms</a><a href="/acceptable-use">Acceptable Use</a><a href="/">Back to PlaceAI</a></nav></header><section class="legal-hero"><span class="legal-kicker">Legal & service terms</span><h1>Terms of Use</h1><p>These terms govern access to PlaceAI unless a separate written agreement with an institution or customer applies.</p><div class="legal-meta">Effective: 12 September 2026</div></section><main class="legal-card"><div class="legal-note">A signed institution or enterprise agreement may contain additional or different terms. If there is a conflict, the signed agreement controls for that customer.</div><h2>1. The service</h2><p>PlaceAI provides software for campus placement operations, student readiness, recruiter workflows, placement drives, interviews, offers, reporting, account administration and AI-assisted decision support.</p><h2>2. Authorized access</h2><p>You may use PlaceAI only through an account and role you are authorized to use. You must provide accurate information, protect credentials, comply with your institution's policies and promptly report suspected unauthorized access. Privileged accounts may be provisioned only by authorized administrators.</p><h2>3. Institution and recruiter responsibilities</h2><p>Institutions and recruiters are responsible for the lawfulness, accuracy and appropriateness of information they submit, the permissions they grant, and employment or placement decisions they make. PlaceAI provides workflow and decision-support tooling; it does not act as an employer, placement agency or guarantor of employment.</p><h2>4. AI-assisted features</h2><p>AI-generated summaries, rankings, recommendations, interview assistance and other outputs can be incomplete or inaccurate. Authorized users must independently review material outputs before relying on them. PlaceAI must not be used to make prohibited or unlawful automated decisions about individuals.</p><h2>5. Acceptable use</h2><p>You must comply with the PlaceAI Acceptable Use Policy. You may not attempt to bypass authorization controls, scrape restricted candidate information, interfere with the service, upload malicious content, impersonate another person or organization, or use PlaceAI in violation of applicable law.</p><h2>6. User and customer content</h2><p>Users and customers retain rights they hold in information they submit. They grant PlaceAI the limited rights necessary to host, process, transmit, secure and display that information to provide the service and satisfy authorized instructions.</p><h2>7. Intellectual property</h2><p>PlaceAI, its software, interfaces, branding and platform materials are protected by applicable intellectual-property laws. Except for rights expressly granted to use the service, no ownership rights are transferred.</p><h2>8. Availability and changes</h2><p>PlaceAI may modify, improve or temporarily suspend parts of the service for maintenance, security, provider outages or operational reasons. Commercial availability commitments, support levels and service-level terms apply only when stated in a separate written agreement.</p><h2>9. Account suspension</h2><p>PlaceAI may restrict or suspend access when reasonably necessary to protect users, institutions, data or infrastructure; investigate abuse; comply with law; or address material violations of these terms. Where appropriate, affected customers will be given notice and a reasonable opportunity to resolve the issue.</p><h2>10. Disclaimers</h2><p>To the extent permitted by applicable law, the service is provided on an "as available" basis unless a separate written agreement states otherwise. PlaceAI does not guarantee placement outcomes, employment offers, candidate suitability, recruiter legitimacy or uninterrupted operation.</p><h2>11. Liability</h2><p>Any liability limitations, indemnities or commercial remedies applicable to an institutional customer should be defined in that customer's signed agreement. Nothing in these public terms excludes rights or liabilities that cannot legally be excluded.</p><h2>12. Governing requirements</h2><p>Use of PlaceAI is subject to applicable law, including applicable privacy, employment, education, cybersecurity and data-protection requirements. Customer-specific governing-law and dispute-resolution terms may be set in signed commercial agreements.</p><h2>13. Changes</h2><p>We may update these terms as PlaceAI evolves. Material changes will be reflected by a revised effective date and, where required, additional notice.</p><h2>14. Contact</h2><p>Questions about these terms should be raised through the PlaceAI access/support channel or the support contact supplied by your institution.</p></main><footer class="legal-footer"><span>© 2026 PlaceAI</span><span><a href="/privacy">Privacy</a> · <a href="/acceptable-use">Acceptable Use</a></span></footer></div></body></html>'''

ACCEPTABLE_USE_HTML = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="PlaceAI Acceptable Use Policy"><title>Acceptable Use — PlaceAI</title><link rel="icon" type="image/svg+xml" href="/static/placeai-icon.svg"><link rel="stylesheet" href="/static/legal.css"><link rel="canonical" href="https://www.placeai.in/acceptable-use">
<meta property="og:type" content="website">
<meta property="og:site_name" content="PlaceAI">
<meta property="og:title" content="Acceptable Use — PlaceAI">
<meta property="og:description" content="PlaceAI Acceptable Use Policy">
<meta property="og:url" content="https://www.placeai.in/acceptable-use">
<meta property="og:image" content="https://www.placeai.in/static/placeai-hero-approved-hd.webp">
<meta property="og:image:alt" content="PlaceAI campus placement collaboration">
<meta name="twitter:card" content="summary_large_image">
<link rel="stylesheet" href="/static/selected-theme.css?v=20261010-readability">
</head><body><div class="legal-shell"><header class="legal-top"><a class="legal-brand" href="/">PlaceAI</a><nav class="legal-nav" aria-label="Legal"><a href="/privacy">Privacy</a><a href="/terms">Terms</a><a href="/acceptable-use">Acceptable Use</a><a href="/">Back to PlaceAI</a></nav></header><section class="legal-hero"><span class="legal-kicker">Platform safeguards</span><h1>Acceptable Use Policy</h1><p>This policy protects students, institutions, recruiters and the PlaceAI service from misuse.</p><div class="legal-meta">Effective: 12 September 2026</div></section><main class="legal-card"><h2>1. Use only authorized data</h2><p>Do not access, upload, export, share or process candidate, institution or recruiter information unless you are authorized to do so. Do not use PlaceAI to create a public candidate directory or bypass institution access controls.</p><h2>2. Protect accounts and credentials</h2><p>Do not share privileged credentials, reuse another user's account, defeat authentication or session controls, probe another tenant, or attempt to obtain passwords, reset tokens, API keys or other secrets.</p><h2>3. No harmful or unlawful activity</h2><p>Do not use PlaceAI for malware, phishing, fraud, harassment, unlawful surveillance, unauthorized scraping, denial-of-service activity, credential attacks, security-control bypasses or any activity that violates applicable law.</p><h2>4. Fair and lawful placement decisions</h2><p>Do not use PlaceAI or its AI features to make unlawful discriminatory decisions. Institutions and recruiters remain responsible for lawful, human-reviewed hiring and placement practices and for independently validating material AI-assisted outputs.</p><h2>5. Recruiter integrity</h2><p>Recruiters must accurately represent their identity, organization, opportunities, compensation and hiring process. False company information, deceptive jobs, unauthorized fee collection, impersonation or misleading placement claims are prohibited.</p><h2>6. Student integrity</h2><p>Students must not intentionally falsify academic records, identity documents, resumes, certifications, application information or interview-related records. Institutions may apply their own disciplinary policies in addition to this policy.</p><h2>7. Platform integrity</h2><p>Do not reverse engineer protected components where prohibited by law, automate excessive requests, circumvent rate limits, interfere with monitoring, exploit vulnerabilities, or use the service in a manner that materially degrades availability for others.</p><h2>8. AI inputs and outputs</h2><p>Do not submit confidential information to AI-assisted features unless its use is authorized for that workflow. AI output must not be presented as verified fact without appropriate human review.</p><h2>9. Enforcement</h2><p>PlaceAI may investigate suspected violations and may restrict access where necessary to protect users, data or infrastructure. Serious violations may be reported to the relevant institution, customer or lawful authority when required.</p><h2>10. Reporting concerns</h2><p>Report suspected abuse, unauthorized access, fraudulent recruiter activity or security issues through the authorized PlaceAI support channel or your institution's placement team.</p></main><footer class="legal-footer"><span>© 2026 PlaceAI</span><span><a href="/privacy">Privacy</a> · <a href="/terms">Terms</a></span></footer></div></body></html>'''

MOCK_INTERVIEW_HTML = '''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="description" content="PlaceAI Secure Placement Assessment — role-aligned, proctored campus assessment with section controls, integrity monitoring and question-level performance analysis.">
  <meta name="theme-color" content="#59416f">
  <title>PlaceAI — Secure Placement Assessment</title>
  <link rel="icon" type="image/svg+xml" href="/static/placeai-icon.svg">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@600;700;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/static/api-errors.css">
  <link rel="stylesheet" href="/static/mock-interview.css?v=20261008-spoken-timer">
  <link rel="stylesheet" href="/static/brand.css">
  <link rel="stylesheet" href="/static/ui-fixes.css">
<link rel="canonical" href="https://www.placeai.in/mock-interview">
<meta property="og:type" content="website">
<meta property="og:site_name" content="PlaceAI">
<meta property="og:title" content="PlaceAI — Secure Placement Assessment">
<meta property="og:description" content="PlaceAI Secure Placement Assessment — role-aligned, proctored campus assessment with section controls, integrity monitoring and question-level performance analysis.">
<meta property="og:url" content="https://www.placeai.in/mock-interview">
<meta property="og:image" content="https://www.placeai.in/static/placeai-hero-approved-hd.webp">
<meta property="og:image:alt" content="PlaceAI campus placement collaboration">
<meta name="twitter:card" content="summary_large_image">
<meta name="robots" content="noindex, nofollow">
<link rel="stylesheet" href="/static/selected-theme.css?v=20261010-readability">
</head>
<body>
<header class="topbar">
  <a class="brand" href="/"><span class="brand-mark"><i></i><i></i><i></i></span><span>PlaceAI</span></a>
  <div class="top-actions">
    <span class="secure"><span class="secure-dot"></span> Interview Intelligence</span>
    <a href="/">Back to PlaceAI</a>
  </div>
</header>

<main class="shell">
  <section class="hero assessment-hero">
    <div class="hero-copy">
      <span class="eyebrow">Secure Placement Assessment</span>
      <h1>Placement Assessment &amp; Interview Simulation</h1><span class="hidden" aria-hidden="true">Mock Interview Coach</span>
      <p>A role-aligned assessment environment for campus placement preparation, combining aptitude, reasoning, communication, technical knowledge, coding, resume defence and behavioural evaluation under structured proctoring controls.</p>
      <div class="hero-meta">
        <span>Role-based blueprint</span><span>Section timers</span><span>Forward-only flow</span><span>Secure browser controls</span><span>AI-assisted proctoring</span>
      </div>
    </div>
    <aside class="hero-score-card assessment-standard-card">
      <span class="card-kicker">Assessment standard</span>
      <strong>Institution-grade simulation</strong>
      <p>Coverage, difficulty, timing and integrity controls are defined by the assessment blueprint. Students complete the assigned structure without reducing or bypassing sections.</p>
      <div class="mini-stats"><div><b>10</b><span>Sections</span></div><div><b>Proctored</b><span>Environment</span></div><div><b>AI + Rules</b><span>Evaluation</span></div></div>
    </aside>
  </section>

  <div id="preview-banner" class="preview-banner hidden"><strong>Assessment preview</strong><span>This preview uses sample assessment data. Camera, screen-share and on-device proctoring checks run when you grant permission; no biometric identity matching is performed.</span></div>
  <div id="auth-state" class="notice">Checking your student session…</div>

  <section id="setup-panel" class="panel hidden">
    <div class="panel-head">
      <div><span class="step">01 · Assessment setup</span><h2>Prepare your placement assessment</h2><p>PlaceAI builds the assessment from the selected opportunity, role requirements and the institution's standardized placement blueprint.</p></div>
      <span class="status-pill">Standardized blueprint</span>
    </div>

    <div class="setup-layout">
      <div>
        <form id="setup-form" class="setup-form"><input type="hidden" value="15" data-legacy-practice-max aria-hidden="true"><input type="hidden" name="difficulty" value="mixed" aria-hidden="true">
          <label>Target opportunity
            <select id="job-select" name="job_id" required><option value="">Loading opportunities…</option></select>
          </label>
          <div class="locked-setting">
            <span>Assessment configuration</span>
            <strong>Standardized placement assessment</strong>
            <small>Coverage, section sequence, difficulty and timing are controlled by the assigned assessment blueprint.</small>
          </div>
          <button class="button primary button-wide" type="submit">Continue to secure system check</button>
        </form>

        <div class="assessment-policy">
          <strong>Secure assessment rules</strong>
          <ul>
            <li>Questions are delivered one at a time and cannot be revisited after moving forward.</li>
            <li>Question content is protected and candidate-watermarked during the assessment.</li>
            <li>Copy/paste, tab switching, full-screen exits, screen-share interruption and supported multi-monitor signals are monitored.</li>
            <li>Camera proctoring checks candidate presence, multiple-person events and visible mobile-phone signals.</li>
            <li>Repeated confirmed integrity warnings can automatically submit the assessment for institutional review.</li>
          </ul>
        </div>
      </div>

      <aside class="blueprint-card">
        <div class="blueprint-title"><span>Assessment map</span><strong>Section-based structure</strong></div>
        <div id="blueprint-list" class="blueprint-list"></div>
        <div class="blueprint-total"><span>Coverage is standardized by role and assessment blueprint.</span><b>10 sections</b></div>
      </aside>
    </div>
  </section>

  <section id="system-panel" class="panel hidden">
    <div class="panel-head">
      <div><span class="step">02 · Secure preflight</span><h2>System &amp; proctoring check</h2><p>Camera, microphone, entire-screen sharing, on-device proctoring, active presence and secure-browser controls must pass before the assessment can begin.</p></div>
      <span id="system-status-pill" class="status-pill neutral">Not checked</span>
    </div>

    <div class="system-grid">
      <div>
        <div class="camera-card">
          <video id="camera-preview" playsinline muted></video>
          <div id="camera-placeholder" class="camera-placeholder"><span>Camera preview</span><small>Your camera feed appears here after permission is granted.</small></div>
          <div class="camera-footer"><span id="device-label">No media access yet</span><span class="live-indicator hidden" id="camera-live">LIVE</span></div>
        </div>
        <div class="liveness-card">
          <div><span class="card-kicker">Active liveness</span><strong id="liveness-title">Not started</strong><small id="liveness-help">Run the system check first. PlaceAI will then verify one-person presence and live movement before entry.</small></div>
          <button id="run-liveness" class="button secondary" type="button" disabled>Run liveness check</button>
        </div>
      </div>

      <div class="checks-card">
        <div class="check-row" data-check="browser"><span class="check-icon">1</span><div><strong>Supported browser</strong><small>Required secure-browser capabilities</small></div><b>Checking</b></div>
        <div class="check-row" data-check="camera"><span class="check-icon">2</span><div><strong>Camera access</strong><small>Continuous candidate and object monitoring</small></div><b>Required</b></div>
        <div class="check-row" data-check="microphone"><span class="check-icon">3</span><div><strong>Microphone access</strong><small>Required for interview and monitored stages</small></div><b>Required</b></div>
        <div class="check-row" data-check="screen"><span class="check-icon">4</span><div><strong>Entire-screen sharing</strong><small>Screen-share interruption is an integrity event</small></div><b>Required</b></div>
        <div class="check-row" data-check="proctor"><span class="check-icon">5</span><div><strong>On-device proctor model</strong><small>Person-count and mobile-phone object detection</small></div><b>Required</b></div>
        <div class="check-row" data-check="liveness"><span class="check-icon">6</span><div><strong>Active presence check</strong><small>Candidate presence plus live movement challenge</small></div><b>Required</b></div>
        <div class="check-row" data-check="fullscreen"><span class="check-icon">7</span><div><strong>Full-screen mode</strong><small>Full-screen exits generate warnings</small></div><b>Required</b></div>
        <div class="check-row" data-check="monitor"><span class="check-icon">8</span><div><strong>Single-monitor check</strong><small>Blocks known extended-display configurations where supported</small></div><b>Checking</b></div>
        <div class="check-row" data-check="clipboard"><span class="check-icon">9</span><div><strong>Clipboard control</strong><small>Copy, paste and context-menu actions are restricted</small></div><b>Enabled</b></div>
        <div class="check-row" data-check="visibility"><span class="check-icon">10</span><div><strong>Focus monitoring</strong><small>Tab and window changes are recorded</small></div><b>Enabled</b></div>
      </div>
    </div>

    <div class="consent-row">
      <label class="consent"><input id="consent-check" type="checkbox"><span>I understand that this proctored assessment uses camera, microphone, entire-screen sharing, full-screen/focus monitoring and on-device object detection for integrity signals. Confirmed warnings are recorded for institutional review. I consent to recording my spoken answers, including camera-and-microphone HR answers, and sending my face, voice and answers to Google Gemini for communication and answer-quality feedback. PlaceAI keeps recordings private for 30 days for me and authorized institution staff. Analysis can continue after submission; the complete result appears together after all sections are ready. This is practice feedback for human review.</span></label>
      <div class="system-actions"><button id="run-check" class="button secondary" type="button">Run system check</button><button id="start-assessment" class="button primary" type="button" disabled>Start proctored assessment</button></div>
    </div>
  </section>

  <section id="interview-panel" class="assessment-shell hidden">
    <aside class="assessment-sidebar">
      <div class="proctor-header">
        <div><span class="proctor-dot"></span><strong>PROCTORED TEST</strong></div>
        <span id="integrity-warning-badge">0 / 4 warnings</span>
      </div>

      <div class="assessment-brand">
        <span class="eyebrow">Live assessment</span>
        <strong id="interview-title">Placement simulation</strong>
        <small id="interview-context"></small>
      </div>

      <div class="timer-card compact-timer">
        <div><span>Total remaining</span><strong id="total-timer">01:45:00</strong></div>
        <div class="progress-track"><i id="total-progress"></i></div>
      </div>

      <div class="assessment-camera-card">
        <video id="assessment-camera" playsinline muted></video>
        <div class="assessment-camera-meta">
          <span><i class="camera-status-dot"></i> Camera live</span>

        </div>
      </div>

      <div class="palette-head">
        <div><strong>Question navigator</strong><small>Forward-only assessment</small></div>
        <span id="palette-progress">0 / 50</span>
      </div>
      <nav id="section-nav" class="section-nav question-navigator" aria-label="Assessment question status"></nav>
      <div class="palette-legend" aria-label="Question status legend">
        <span><i class="legend-dot attempted"></i>Attempted</span>
        <span><i class="legend-dot current"></i>Current</span>
        <span><i class="legend-dot unattempted"></i>Not attempted</span>
      </div>

      <div class="integrity-summary">
        <span><i class="integrity-dot"></i> Secure monitoring active</span>
        <small id="integrity-count">0 integrity events</small>
      </div>
    </aside>

    <div class="assessment-main">
      <div id="proctor-warning-banner" class="proctor-warning-banner hidden" role="alert" aria-live="assertive">
        <div><span>Integrity warning</span><strong id="proctor-warning-title">Proctoring event detected</strong><small id="proctor-warning-detail"></small></div>
        <b id="proctor-warning-count">1 / 4</b>
      </div>

      <div class="assessment-toolbar">
        <div><span id="section-label">Section</span><strong id="question-progress">Question 1 of 50</strong></div>
        <div class="toolbar-right">
          <div class="section-clock"><small>Section</small><span id="section-timer">12:00</span></div>
          <span class="forward-badge">Forward-only</span>
          <span class="proctor-live-badge" title="Camera and exam activity monitoring"><svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="3" fill="currentColor"/></svg> <b id="camera-proctor-status">Monitoring active</b></span>
        </div>
      </div>

      <div class="question-stage">
        <div class="question-badges"><span id="question-section" class="category"></span><span id="question-difficulty" class="category"></span><span class="category secure-question">Protected question</span></div>
        <div id="question-canvas-wrap" class="protected-question">
          <p id="question-text" class="readable-question"></p><small id="question-watermark" class="question-watermark"></small>
        </div>
        <p id="question-guidance" class="question-guidance">Read the question and choose your answer. Save the current response, then use Save &amp; Next to permanently move forward.</p>
        <div id="answer-area" class="answer-area"></div>
      </div>

      <div class="assessment-actionbar">
        <div>
          <span id="autosave-state">Response not saved</span>
          <small>Once you move forward, this question cannot be reopened.</small>
        </div>
        <div class="assessment-action-buttons">
          <button id="save-question" class="button secondary" type="button">Save answer</button>
          <button id="next-question" class="button primary" type="button">Save &amp; Next</button>
        </div>
      </div>
    </div>
  </section>

  <section id="analysis-panel" class="panel analysis-panel hidden">
    <div class="analysis-head">
      <div class="analysis-spinner" aria-hidden="true"><i></i><i></i><i></i></div>
      <div><span class="step">03 · Deep answer analysis</span><h2>PlaceAI is grading every response</h2><p id="analysis-message">Checking system-graded answers and preparing question-level AI evaluation.</p></div>
    </div>
    <div class="analysis-steps">
      <div class="analysis-step active" data-analysis-step="objective"><span>01</span><div><strong>Objective grading</strong><small>Compare MCQ responses with protected server-side answer keys.</small></div><b>Running</b></div>
      <div class="analysis-step" data-analysis-step="subjective"><span>02</span><div><strong>AI answer evaluation</strong><small>Score each open-ended response for correctness, relevance, reasoning and completeness.</small></div><b>Queued</b></div>
      <div class="analysis-step" data-analysis-step="sections"><span>03</span><div><strong>Section analytics</strong><small>Aggregate question scores without hiding weak sections behind a single average.</small></div><b>Queued</b></div>
      <div class="analysis-step" data-analysis-step="plan"><span>04</span><div><strong>Coaching report</strong><small>Build corrections, ideal approaches, weak-topic diagnosis and next-practice actions.</small></div><b>Queued</b></div>
    </div>
    <div class="analysis-note"><strong>No instant guessed score.</strong><span>All section results appear together after answer grading and HR video analysis are complete. If AI evaluation fails, PlaceAI withholds the final score instead of fabricating one.</span></div>
    <div class="form-actions"><button id="retry-analysis" class="button secondary hidden" type="button">Retry analysis</button><button id="return-to-setup" class="button secondary hidden" type="button">Return to assessment setup</button></div>
  </section>

  <section id="result-panel" class="panel result-panel hidden">
    <div class="panel-head result-head">
      <div><span class="step">04 · Assessment intelligence</span><h2>Complete performance report</h2><p>Answer-key correctness, sandbox-executed coding, AI-evaluated descriptive answers and integrity signals are shown separately.</p></div>
      <div class="score-badge"><strong id="overall-score">—</strong><span>/100 IRI</span></div>
    </div>

    <div id="analysis-status-banner" class="result-alert hidden"></div>

    <section id="hr-video-report" class="result-section hidden">
      <div class="result-section-head"><div><span class="card-kicker">Recorded HR answers</span><h3>Your communication and answer feedback</h3></div></div>
      <p id="hr-video-summary"></p>
      <p id="hr-playback-status" class="disclaimer" role="status"></p>
      <button id="load-hr-recording" type="button" class="button secondary">Load private recording</button>
      <video id="hr-result-video" class="hidden" controls playsinline preload="none" aria-label="Your private HR answer recording" style="width:100%;max-height:480px"></video>
    </section>

    <div class="result-hero-grid">
      <article class="report-card performance">
        <span>Interview Readiness Index</span>
        <strong id="report-iri">—</strong>
        <p id="overall-feedback">Complete the assessment to generate evidence-based coaching.</p>
        <div class="grading-method"><span>Grading</span><b id="grading-method-label">Answer key + sandbox + question-level AI</b></div>
      </article>
      <article class="report-card integrity">
        <span>Assessment integrity</span>
        <strong id="integrity-status">Review ready</strong>
        <p id="integrity-summary-text">Integrity events are surfaced for human review and are not treated as proof of misconduct.</p>
        <div class="integrity-result-meta"><span>Warnings</span><b id="result-warning-count">0 / 4</b></div>
      </article>
    </div>

    <div class="score-summary-grid">
      <article class="score-stat"><span>Total</span><strong id="summary-total">—</strong><small>questions</small></article>
      <article class="score-stat"><span>Correct / strong</span><strong id="summary-correct">—</strong><small>responses</small></article>
      <article class="score-stat partial"><span>Partial / acceptable</span><strong id="summary-partial">—</strong><small>responses</small></article>
      <article class="score-stat wrong"><span>Incorrect / weak</span><strong id="summary-incorrect">—</strong><small>responses</small></article>
      <article class="score-stat insufficient"><span>Unanswered / insufficient</span><strong id="summary-insufficient">—</strong><small>responses</small></article>
      <article class="score-stat"><span>Objective accuracy</span><strong id="summary-objective">—</strong><small>system graded</small></article>
      <article class="score-stat"><span>Open-ended average</span><strong id="summary-subjective">—</strong><small>AI + relevance gate</small></article>
      <article class="score-stat"><span>Coding tests</span><strong id="summary-coding">—</strong><small>passed / total</small></article>
    </div>

    <section id="integrity-report-panel" class="result-section integrity-report-section">
      <div class="result-section-head">
        <div><span class="card-kicker">Proctoring evidence</span><h3>Integrity timeline</h3><p>Browser, camera and AI-vision signals are recorded separately from academic performance.</p></div>
        <div class="integrity-institution"><span>Institution</span><strong id="integrity-institution-name">—</strong></div>
      </div>
      <div id="integrity-termination-note" class="integrity-termination-note hidden"></div>
      <div id="integrity-event-list" class="integrity-event-list"></div>
    </section>

    <section class="result-section">
      <div class="result-section-head"><div><span class="card-kicker">Section performance</span><h3>Where the score came from</h3></div><p>No section is hidden behind the overall score.</p></div>
      <div class="section-table-wrap">
        <table class="section-table">
          <thead><tr><th>Section</th><th>Score</th><th>Correct/Strong</th><th>Partial</th><th>Wrong/Weak</th><th>Insufficient</th><th>Evaluated</th></tr></thead>
          <tbody id="section-performance"></tbody>
        </table>
      </div>
    </section>

    <section class="result-section">
      <div class="result-section-head"><div><span class="card-kicker">Competency profile</span><h3>Section score distribution</h3></div></div>
      <div id="dimension-grid" class="dimension-grid"></div>
    </section>

    <div class="two-col result-coaching">
      <article class="feedback-box good"><h3>Strongest areas</h3><ul id="strength-list"></ul></article>
      <article class="feedback-box"><h3>Highest-value improvements</h3><ul id="improvement-list"></ul></article>
    </div>
    <div class="two-col">
      <article class="feedback-box"><h3>Weak topics to revise</h3><ul id="weak-topic-list"></ul></article>
      <article class="feedback-box good"><h3>Next practice plan</h3><ol id="practice-plan-list"></ol></article>
    </div>

    <section class="result-section question-review-section">
      <div class="result-section-head">
        <div><span class="card-kicker">Question-level report</span><h3>Review every answer</h3><p>See your response, verdict, score, correct answer or AI reasoning, missing points and a stronger approach.</p></div>
        <div class="review-filters" id="review-filters">
          <button class="review-filter active" type="button" data-review-filter="all">All</button>
          <button class="review-filter" type="button" data-review-filter="correct">Correct / strong</button>
          <button class="review-filter" type="button" data-review-filter="partial">Partial</button>
          <button class="review-filter" type="button" data-review-filter="incorrect">Wrong / weak</button>
          <button class="review-filter" type="button" data-review-filter="insufficient">Insufficient</button>
        </div>
      </div>
      <div id="answer-feedback" class="answer-feedback detailed-feedback"></div>
    </section>

    <p id="result-disclaimer" class="disclaimer"></p>
    <p id="report-email-status" class="disclaimer" role="status"></p>
    <div class="form-actions result-actions">
      <button id="retry-analysis-result" class="button secondary hidden" type="button">Retry incomplete AI analysis</button>
      <button class="button primary" id="practice-again" type="button">Return to assessment setup</button>
    </div>
  </section>

  <section id="history-panel" class="panel hidden">
    <div class="panel-head"><div><span class="step">Progress</span><h2>Previous attempts</h2><p>Track improvement across role-specific simulations.</p></div></div>
    <div id="history-list" class="history-list"></div>
  </section>
</main>

<div id="integrity-overlay" class="integrity-overlay hidden" role="dialog" aria-modal="true">
  <div class="integrity-dialog">
    <span class="card-kicker">Assessment paused</span>
    <h2 id="integrity-overlay-title">Secure full-screen was interrupted</h2>
    <p id="integrity-overlay-text">This event has been added to the integrity timeline. Restore the secure environment to continue.</p>
    <div class="integrity-warning-meter">Warning <strong id="overlay-warning-number">1</strong> of <strong>4</strong></div>
    <button id="restore-secure-mode" class="button primary" type="button">Restore secure mode</button>
  </div>
</div>

<div id="toast" class="toast hidden" role="status" aria-live="polite"></div>
<script src="/static/api-errors.js" defer></script>
<script src="https://cdn.jsdelivr.net/npm/@tensorflow/tfjs@4.22.0/dist/tf.es2017.min.js" defer></script>
<script src="https://cdn.jsdelivr.net/npm/@tensorflow-models/coco-ssd@2.2.3/dist/coco-ssd.min.js" defer></script>
<script src="/static/mock-interview.js?v=20261010-readable-fonts" defer></script>
</body>
</html>
'''

NOT_FOUND_HTML = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>Page not found — PlaceAI</title><link rel="icon" href="/static/placeai-icon.svg"><link rel="stylesheet" href="/static/legal.css"><link rel="stylesheet" href="/static/selected-theme.css?v=20261010-readability">
</head>
<body><div class="legal-shell"><header class="legal-top"><a class="legal-brand" href="/">PlaceAI</a></header><main class="legal-card"><p>404 · Page not found</p><h1>Let’s get you back to PlaceAI.</h1><p>This page may have moved, or the address may be incomplete. Your account and saved assessments are unaffected.</p><p><a href="/">Open PlaceAI</a> · <a href="/mock-interview">Open Interview Intelligence</a> · <a href="/static/contact.html">Contact support</a></p></main></div></body></html>
'''

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
  <meta name="theme-color" content="#071f45">
  <title>PlaceAI — Campus placement operations</title>
  <link rel="icon" type="image/svg+xml" href="/static/placeai-icon.svg">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/static/app.css">
  <link rel="stylesheet" href="/static/brand.css">
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
          <p class="hero-lead">Manage student readiness, approved opportunities, placement drives, recruiter pipelines, interviews, offers and reporting from one controlled workspace.</p>
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
          <div class="production-surface-card">
            <div>
              <span class="surface-kicker">Production workspace</span>
              <h3>Real records appear only after authenticated users create them.</h3>
              <p>PlaceAI does not display fabricated students, companies, applications, placement rates or operational activity on its public surface.</p>
            </div>
            <div class="production-surface-grid">
              <div><strong>Student</strong><span>Profile, eligibility, applications, documents and interview preparation.</span></div>
              <div><strong>Recruiter</strong><span>Approved jobs, applicant pipelines, interviews, offers and company verification.</span></div>
              <div><strong>Institution Admin</strong><span>Students, recruiters, drives, approvals, attendance, governance and reports.</span></div>
              <div><strong>Platform Admin</strong><span>Institution provisioning, access review and platform operations.</span></div>
            </div>
          </div>
        </div>
      </section>

      <section class="proof-strip">
        <div class="section-shell proof-content">
          <span>Designed to replace fragmented placement operations across</span>
          <strong>Spreadsheets</strong><i></i><strong>Messaging threads</strong><i></i><strong>Scattered résumés</strong><i></i><strong>Manual reports</strong>
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
          <article class="bento-card bento-wide"><span class="card-number">04</span><div><h3>Student readiness</h3><p>Profile completion, résumé records, documents, interview preparation and application history are tied to the signed-in student account.</p></div></article>
        </div>
      </section>

      <section id="institutions" class="dark-section">
        <div class="section-shell dark-grid">
          <div class="dark-copy">
            <span class="section-kicker light">For placement teams</span>
            <h2>Operate placement workflows with institutional control.</h2>
            <p>Provision authorized users, verify student records, review campus jobs, configure drives, manage attendance and export placement data without exposing candidate information as a public directory.</p>
            <ul class="check-list">
              <li>Institution-scoped student records and verification</li>
              <li>Controlled recruiter provisioning and campus-job approval</li>
              <li>Drive eligibility by configured academic criteria</li>
              <li>Application, interview, offer and placement outcome tracking</li>
              <li>Audit, policy, incident and reporting workflows</li>
            </ul>
            <button class="button button-light button-large" data-open-access="request">Request institution access</button>
          </div>
          <div class="production-surface-card">
            <div><span class="surface-kicker">Institution controls</span><h3>Tenant-scoped workflows by design.</h3><p>Institution administrators work inside their authorized organization. Recruiter access, jobs, students and placement records remain subject to backend authorization checks.</p></div>
          </div>
        </div>
      </section>

      <section id="recruiters" class="section-shell role-section">
        <div class="section-heading compact">
          <div><span class="section-kicker">For hiring teams</span><h2>Manage approved campus hiring<br>without exposing a public candidate directory.</h2></div>
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
            <div><strong>Verified role selection</strong><span>The selected sign-in role must match the account's backend role.</span></div>
            <div><strong>Institution tenancy</strong><span>Student and campus data is scoped to authorized organizations.</span></div>
            <div><strong>Secure recovery</strong><span>Password reset uses one-time server-side state and does not enumerate accounts.</span></div>
            <div><strong>AI fallback safety</strong><span>AI unavailability does not create fabricated candidate analysis.</span></div>
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

  <div id="auth-overlay" class="modal-overlay hidden" role="dialog" aria-modal="true" aria-labelledby="auth-title">
    <div class="auth-modal">
      <button class="modal-close" data-action="close-auth" aria-label="Close">×</button>
      <div class="auth-brand-panel"><a class="brand brand-light" href="#"><span class="brand-mark"><span></span><span></span><span></span></span><span>PlaceAI</span></a><div><span class="auth-panel-kicker">Controlled access</span><h2>One secure entry point for every PlaceAI workspace.</h2><p>Select the role assigned to your account. Privileged roles require authorized provisioning.</p></div><div class="auth-proof"><span>Role verification</span><span>Institution tenancy</span><span>Privacy-first candidate access</span></div></div>
      <div class="auth-form-panel">
        <div id="login-view"><span class="section-kicker">Secure access</span><h2 id="auth-title">Sign in to PlaceAI</h2></div>
        <div id="signup-view" class="hidden"><span class="section-kicker">Account access</span><h2 id="auth-create-title">Create or request access</h2></div>
        <div id="reset-view" class="hidden"><span class="section-kicker">Account recovery</span><h2 id="auth-reset-title">Reset your password</h2><p class="form-intro">Enter your email. If the account exists, PlaceAI will send a one-time reset link when transactional email is configured.</p><form id="forgot-form" class="form-stack"><label>Email address<input type="email" name="email" required autocomplete="email"></label><button class="button button-primary button-full">Send reset link</button></form><button class="text-button back-link" data-action="show-login">← Back to sign in</button></div>
      </div>
    </div>
  </div>

  <div id="generic-modal" class="modal-overlay hidden" role="dialog" aria-modal="true" aria-label="Dialog">
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
</html>'''

PRIVACY_HTML = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="PlaceAI Privacy Policy"><title>Privacy Policy — PlaceAI</title><link rel="icon" type="image/svg+xml" href="/static/placeai-icon.svg"><link rel="stylesheet" href="/static/legal.css"></head><body><div class="legal-shell"><header class="legal-top"><a class="legal-brand" href="/">PlaceAI</a><nav class="legal-nav" aria-label="Legal"><a href="/privacy">Privacy</a><a href="/terms">Terms</a><a href="/acceptable-use">Acceptable Use</a><a href="/">Back to PlaceAI</a></nav></header><section class="legal-hero"><span class="legal-kicker">Legal & privacy</span><h1>Privacy Policy</h1><p>This policy explains how PlaceAI handles personal and institutional information when providing campus placement operations, applicant workflows, recruiter tools and AI-assisted features.</p><div class="legal-meta">Effective: 12 September 2026</div></section><main class="legal-card"><div class="legal-note">PlaceAI is designed for controlled institutional use. Institution-specific contractual or data-processing terms may provide additional protections and take precedence where applicable.</div><h2>1. Information we process</h2><p>Depending on your role and the features your institution enables, PlaceAI may process account and identity information; academic and student profile information; resumes and supporting documents; job applications, eligibility results, interviews, attendance and offers; recruiter and company verification information; communications, audit events and security logs; and technical information necessary to operate and secure the service.</p><h2>2. Why we process information</h2><p>We use information to authenticate users, provide role-based placement workflows, manage institution and recruiter operations, evaluate configured eligibility criteria, support interview and application workflows, send account and security communications, prevent abuse, maintain auditability, diagnose service issues and provide authorized AI-assisted analysis.</p><h2>3. Institutions and authorized users</h2><p>For institution-managed records, the relevant institution may determine why and how student or placement information is used. PlaceAI processes that information to provide the service and according to the institution's authorized configuration, applicable agreements and law. Users must only access information they are authorized to handle.</p><h2>4. AI-assisted features</h2><p>PlaceAI may send the minimum information necessary for a requested AI feature to configured AI service providers. OpenAI is the primary AI provider and Google Gemini may be used as a fallback when configured. AI output is decision support only and is intended for authorized human review. PlaceAI does not represent AI output as a guaranteed hiring, placement or eligibility decision.</p><h2>5. Service providers and international processing</h2><p>PlaceAI uses infrastructure and communications providers to host the application, database, transactional email and AI functionality. These providers may process information in jurisdictions outside the user's location. PlaceAI limits provider access to what is necessary to deliver and secure the service.</p><h2>6. Cookies and session information</h2><p>PlaceAI uses essential authentication and security mechanisms required to sign users in, maintain authorized sessions and protect accounts. PlaceAI does not require advertising cookies to operate the placement workspace.</p><h2>7. Retention</h2><p>Information is retained for as long as required to provide the service, satisfy institutional instructions, preserve legitimate security and audit records, meet contractual obligations or comply with applicable law. Retention requirements may vary by institution and record type.</p><h2>8. Security</h2><p>PlaceAI uses role-based authorization, institution scoping, encrypted HTTPS transport, secure password handling, session controls, audit records, rate limiting, security headers, dependency scanning and production health checks. No online service can guarantee absolute security, so suspected security incidents should be reported promptly through the authorized PlaceAI support channel.</p><h2>9. Your choices and rights</h2><p>Users may request access, correction or other action concerning personal information through their institution where the institution manages that information, or through the PlaceAI support/access channel for platform-managed information. Requests are handled subject to identity verification, institutional responsibilities and applicable law.</p><h2>10. Student and age considerations</h2><p>PlaceAI is intended primarily for higher-education placement operations. Institutions are responsible for ensuring that accounts and student information are collected and used with the appropriate authority, notice or consent required by applicable law.</p><h2>11. Changes to this policy</h2><p>We may update this policy when the service, providers, legal requirements or data practices change. The effective date above will be updated when material revisions are published.</p><h2>12. Contact</h2><p>For privacy or data-handling questions, use the PlaceAI access/support channel or the support contact supplied by your institution. Security vulnerabilities should be reported through the process described in PlaceAI's Security Policy.</p></main><footer class="legal-footer"><span>© 2026 PlaceAI</span><span><a href="/terms">Terms</a> · <a href="/acceptable-use">Acceptable Use</a></span></footer></div></body></html>'''

TERMS_HTML = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="PlaceAI Terms of Use"><title>Terms of Use — PlaceAI</title><link rel="icon" type="image/svg+xml" href="/static/placeai-icon.svg"><link rel="stylesheet" href="/static/legal.css"></head><body><div class="legal-shell"><header class="legal-top"><a class="legal-brand" href="/">PlaceAI</a><nav class="legal-nav" aria-label="Legal"><a href="/privacy">Privacy</a><a href="/terms">Terms</a><a href="/acceptable-use">Acceptable Use</a><a href="/">Back to PlaceAI</a></nav></header><section class="legal-hero"><span class="legal-kicker">Legal & service terms</span><h1>Terms of Use</h1><p>These terms govern access to PlaceAI unless a separate written agreement with an institution or customer applies.</p><div class="legal-meta">Effective: 12 September 2026</div></section><main class="legal-card"><div class="legal-note">A signed institution or enterprise agreement may contain additional or different terms. If there is a conflict, the signed agreement controls for that customer.</div><h2>1. The service</h2><p>PlaceAI provides software for campus placement operations, student readiness, recruiter workflows, placement drives, interviews, offers, reporting, account administration and AI-assisted decision support.</p><h2>2. Authorized access</h2><p>You may use PlaceAI only through an account and role you are authorized to use. You must provide accurate information, protect credentials, comply with your institution's policies and promptly report suspected unauthorized access. Privileged accounts may be provisioned only by authorized administrators.</p><h2>3. Institution and recruiter responsibilities</h2><p>Institutions and recruiters are responsible for the lawfulness, accuracy and appropriateness of information they submit, the permissions they grant, and employment or placement decisions they make. PlaceAI provides workflow and decision-support tooling; it does not act as an employer, placement agency or guarantor of employment.</p><h2>4. AI-assisted features</h2><p>AI-generated summaries, rankings, recommendations, interview assistance and other outputs can be incomplete or inaccurate. Authorized users must independently review material outputs before relying on them. PlaceAI must not be used to make prohibited or unlawful automated decisions about individuals.</p><h2>5. Acceptable use</h2><p>You must comply with the PlaceAI Acceptable Use Policy. You may not attempt to bypass authorization controls, scrape restricted candidate information, interfere with the service, upload malicious content, impersonate another person or organization, or use PlaceAI in violation of applicable law.</p><h2>6. User and customer content</h2><p>Users and customers retain rights they hold in information they submit. They grant PlaceAI the limited rights necessary to host, process, transmit, secure and display that information to provide the service and satisfy authorized instructions.</p><h2>7. Intellectual property</h2><p>PlaceAI, its software, interfaces, branding and platform materials are protected by applicable intellectual-property laws. Except for rights expressly granted to use the service, no ownership rights are transferred.</p><h2>8. Availability and changes</h2><p>PlaceAI may modify, improve or temporarily suspend parts of the service for maintenance, security, provider outages or operational reasons. Commercial availability commitments, support levels and service-level terms apply only when stated in a separate written agreement.</p><h2>9. Account suspension</h2><p>PlaceAI may restrict or suspend access when reasonably necessary to protect users, institutions, data or infrastructure; investigate abuse; comply with law; or address material violations of these terms. Where appropriate, affected customers will be given notice and a reasonable opportunity to resolve the issue.</p><h2>10. Disclaimers</h2><p>To the extent permitted by applicable law, the service is provided on an "as available" basis unless a separate written agreement states otherwise. PlaceAI does not guarantee placement outcomes, employment offers, candidate suitability, recruiter legitimacy or uninterrupted operation.</p><h2>11. Liability</h2><p>Any liability limitations, indemnities or commercial remedies applicable to an institutional customer should be defined in that customer's signed agreement. Nothing in these public terms excludes rights or liabilities that cannot legally be excluded.</p><h2>12. Governing requirements</h2><p>Use of PlaceAI is subject to applicable law, including applicable privacy, employment, education, cybersecurity and data-protection requirements. Customer-specific governing-law and dispute-resolution terms may be set in signed commercial agreements.</p><h2>13. Changes</h2><p>We may update these terms as PlaceAI evolves. Material changes will be reflected by a revised effective date and, where required, additional notice.</p><h2>14. Contact</h2><p>Questions about these terms should be raised through the PlaceAI access/support channel or the support contact supplied by your institution.</p></main><footer class="legal-footer"><span>© 2026 PlaceAI</span><span><a href="/privacy">Privacy</a> · <a href="/acceptable-use">Acceptable Use</a></span></footer></div></body></html>'''

ACCEPTABLE_USE_HTML = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="PlaceAI Acceptable Use Policy"><title>Acceptable Use — PlaceAI</title><link rel="icon" type="image/svg+xml" href="/static/placeai-icon.svg"><link rel="stylesheet" href="/static/legal.css"></head><body><div class="legal-shell"><header class="legal-top"><a class="legal-brand" href="/">PlaceAI</a><nav class="legal-nav" aria-label="Legal"><a href="/privacy">Privacy</a><a href="/terms">Terms</a><a href="/acceptable-use">Acceptable Use</a><a href="/">Back to PlaceAI</a></nav></header><section class="legal-hero"><span class="legal-kicker">Platform safeguards</span><h1>Acceptable Use Policy</h1><p>This policy protects students, institutions, recruiters and the PlaceAI service from misuse.</p><div class="legal-meta">Effective: 12 September 2026</div></section><main class="legal-card"><h2>1. Use only authorized data</h2><p>Do not access, upload, export, share or process candidate, institution or recruiter information unless you are authorized to do so. Do not use PlaceAI to create a public candidate directory or bypass institution access controls.</p><h2>2. Protect accounts and credentials</h2><p>Do not share privileged credentials, reuse another user's account, defeat authentication or session controls, probe another tenant, or attempt to obtain passwords, reset tokens, API keys or other secrets.</p><h2>3. No harmful or unlawful activity</h2><p>Do not use PlaceAI for malware, phishing, fraud, harassment, unlawful surveillance, unauthorized scraping, denial-of-service activity, credential attacks, security-control bypasses or any activity that violates applicable law.</p><h2>4. Fair and lawful placement decisions</h2><p>Do not use PlaceAI or its AI features to make unlawful discriminatory decisions. Institutions and recruiters remain responsible for lawful, human-reviewed hiring and placement practices and for independently validating material AI-assisted outputs.</p><h2>5. Recruiter integrity</h2><p>Recruiters must accurately represent their identity, organization, opportunities, compensation and hiring process. False company information, deceptive jobs, unauthorized fee collection, impersonation or misleading placement claims are prohibited.</p><h2>6. Student integrity</h2><p>Students must not intentionally falsify academic records, identity documents, resumes, certifications, application information or interview-related records. Institutions may apply their own disciplinary policies in addition to this policy.</p><h2>7. Platform integrity</h2><p>Do not reverse engineer protected components where prohibited by law, automate excessive requests, circumvent rate limits, interfere with monitoring, exploit vulnerabilities, or use the service in a manner that materially degrades availability for others.</p><h2>8. AI inputs and outputs</h2><p>Do not submit confidential information to AI-assisted features unless its use is authorized for that workflow. AI output must not be presented as verified fact without appropriate human review.</p><h2>9. Enforcement</h2><p>PlaceAI may investigate suspected violations and may restrict access where necessary to protect users, data or infrastructure. Serious violations may be reported to the relevant institution, customer or lawful authority when required.</p><h2>10. Reporting concerns</h2><p>Report suspected abuse, unauthorized access, fraudulent recruiter activity or security issues through the authorized PlaceAI support channel or your institution's placement team.</p></main><footer class="legal-footer"><span>© 2026 PlaceAI</span><span><a href="/privacy">Privacy</a> · <a href="/terms">Terms</a></span></footer></div></body></html>'''

MOCK_INTERVIEW_HTML = '''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="description" content="PlaceAI Mock Interview Coach for student placement preparation.">
  <meta name="theme-color" content="#071f45">
  <title>PlaceAI — Mock Interview Coach</title>
  <link rel="icon" type="image/svg+xml" href="/static/placeai-icon.svg">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@600;700;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/static/api-errors.css">
  <link rel="stylesheet" href="/static/mock-interview.css">
  <link rel="stylesheet" href="/static/brand.css">
</head>
<body>
  <header class="topbar">
    <a class="brand" href="/"><span class="brand-mark"><i></i><i></i><i></i></span><span>PlaceAI</span></a>
    <div class="top-actions"><span class="secure">Student coaching workspace</span><a href="/">Back to PlaceAI</a></div>
  </header>

  <main class="shell">
    <section class="hero">
      <div>
        <span class="eyebrow">AI-assisted preparation</span>
        <h1>Mock Interview Coach</h1>
        <p>Practice against a real PlaceAI opportunity with role-specific, non-repeating questions. After each round, receive question-by-question analysis, missing concepts, stronger answer structures, example solutions and a targeted next-practice plan.</p>
      </div>
      <div class="guardrail"><strong>Text-only coaching</strong><span>Scores are preparation signals. They do not measure accent, spoken fluency, personality or employability.</span></div>
    </section>

    <div id="auth-state" class="notice">Checking your student session…</div>

    <section id="setup-panel" class="panel hidden">
      <div class="panel-head"><div><span class="step">01</span><h2>Configure the practice round</h2><p>Choose the role, focus, difficulty and round length. PlaceAI avoids questions used in your recent attempts for the same role.</p></div></div>
      <form id="setup-form" class="setup-grid">
        <label>Opportunity<select id="job-select" name="job_id" required><option value="">Loading opportunities…</option></select></label>
        <label>Interview focus<select name="focus"><option value="balanced">Balanced</option><option value="technical">Technical</option><option value="behavioral">Behavioral</option><option value="hr">HR / communication</option></select></label>
        <label>Difficulty<select name="difficulty"><option value="mixed" selected>Mixed progression</option><option value="easy">Foundation</option><option value="medium">Intermediate</option><option value="hard">Advanced</option></select></label>
        <label>Mode<select name="mode"><option value="practice" selected>Practice + coaching</option><option value="assessment">Assessment simulation</option></select></label>
        <label>Questions<select name="question_count"><option value="5">5 questions</option><option value="8" selected>8 questions</option><option value="10">10 questions</option><option value="12">12 questions</option><option value="15">15 questions</option></select></label>
        <button class="button primary" type="submit">Generate new interview</button>
      </form>
    </section>

    <section id="interview-panel" class="panel hidden">
      <div class="panel-head"><div><span class="step">02</span><h2 id="interview-title">Answer the interview</h2><p id="interview-context"></p></div><span class="status-pill">Human practice · AI coaching</span></div>
      <form id="interview-form"><div id="question-list" class="question-list"></div><div class="form-actions"><button type="button" class="button secondary" id="restart-button">Start over</button><button class="button primary" type="submit">Finish & analyse answers</button></div></form>
    </section>

    <section id="result-panel" class="panel hidden">
      <div class="panel-head"><div><span class="step">03</span><h2>Your interview analysis</h2><p>Use the evidence below to improve the next attempt.</p></div><div class="score-badge"><strong id="overall-score">—</strong><span>/100</span></div></div>
      <p id="overall-feedback" class="overall-feedback"></p>
      <div id="dimension-grid" class="dimension-grid"></div>
      <div class="two-col"><article class="feedback-box good"><h3>Strengths</h3><ul id="strength-list"></ul></article><article class="feedback-box"><h3>Highest-value improvements</h3><ul id="improvement-list"></ul></article></div>
      <div class="two-col"><article class="feedback-box"><h3>Weak topics to revise</h3><ul id="weak-topic-list"></ul></article><article class="feedback-box good"><h3>Next practice plan</h3><ol id="practice-plan-list"></ol></article></div>
      <div id="answer-feedback" class="answer-feedback"></div><p id="result-disclaimer" class="disclaimer"></p><div class="form-actions"><button class="button primary" id="practice-again" type="button">Generate another fresh round</button></div>
    </section>

    <section id="history-panel" class="panel hidden"><div class="panel-head"><div><span class="step">History</span><h2>Previous attempts</h2><p>Your recent evaluated rounds are also used to avoid repeating questions for the same role.</p></div></div><div id="history-list" class="history-list"></div></section>
  </main>

  <div id="toast" class="toast hidden" role="status" aria-live="polite"></div>
  <script src="/static/api-errors.js" defer></script>
  <script src="/static/mock-interview.js" defer></script>
</body>
</html>'''

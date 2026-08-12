# Security Policy

## Supported Versions

KnowFlow is currently an early-stage project without versioned releases. Only
the latest commit on the `main` branch receives security fixes.

## Deployment Boundary

KnowFlow is designed as a local, single-user application. The API has no user
authentication, authorization, tenant isolation, or rate limiting. Do not
expose the backend, SQLite database, upload directory, or Chroma data directory
to an untrusted network. A public or multi-user deployment is unsupported until
those controls are added.

Uploaded files and retrieved document text are untrusted input. API keys must
remain in `backend/.env` or another secret store and must never be committed.
Operators are responsible for reviewing what content is sent to configured LLM
and embedding providers.

## Reporting a Vulnerability

Please use GitHub's private vulnerability reporting for this repository:

https://github.com/LBStruggleee/KnowFlow/security/advisories/new

Do not disclose the vulnerability in a public issue or pull request. Include:

- the affected file, endpoint, or revision;
- the prerequisites and reproducible steps;
- the expected security impact;
- a minimal proof of concept, if safe to provide; and
- any suggested mitigation.

Never include real API keys, private documents, or unrelated personal data in
a report. You may use placeholder credentials and synthetic test files.

The maintainer will acknowledge a complete report within seven days, assess
its impact, and coordinate remediation and disclosure. This is a response
target, not a guaranteed resolution deadline. Please allow a reasonable period
for a fix before public disclosure.

## Security-Sensitive Areas

Reports are especially useful for prompt injection through retrieved content,
malformed or resource-exhausting PDF/DOCX/PPTX inputs, unsafe file paths or
deletion, unauthorized API access, credential or document leakage through
outbound requests or logs, and dependency or CI supply-chain compromise.

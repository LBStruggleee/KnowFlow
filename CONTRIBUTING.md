# Contributing to KnowFlow

Thank you for contributing to KnowFlow. The project welcomes focused bug
fixes, tests, documentation improvements, security hardening, and features
that support its local-first educational RAG use case.

## Before You Start

- Search existing issues and pull requests before proposing duplicate work.
- Open an issue before a large change so its scope and design can be agreed on.
- Do not include API keys, private documents, generated databases, vector
  indexes, logs, or other user data in commits, tests, or issue reports.
- Report vulnerabilities through the process in [SECURITY.md](SECURITY.md), not
  through a public issue.

## Development Setup

The backend requires Python 3.13. From the repository root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
$env:PYTHONPATH = "."
pytest tests -q
ruff check .
ruff format --check .
```

For the frontend:

```powershell
cd frontend
npm ci
npm test
npm run build
```

Use the placeholder values in the example environment files. Tests and pull
requests must not depend on a maintainer's live API credentials.

## Pull Requests

- Keep each pull request limited to one coherent change.
- Explain the user-visible behavior, security implications, and verification
  performed.
- Add or update tests for behavior changes and regressions.
- Update documentation when APIs, configuration, deployment boundaries, or
  supported file formats change.
- Preserve the local-only security boundary unless the change also provides
  authentication, authorization, rate limiting, and appropriate data isolation.
- Treat uploaded documents and retrieved text as untrusted input. Changes to
  parsing, prompt construction, file handling, outbound requests, CI, or
  dependencies require explicit security review.

All required GitHub Actions checks should pass before merge. A passing CI run
does not replace maintainer review.

## Commit Messages

Use concise imperative messages. Conventional prefixes such as `feat:`,
`fix:`, `docs:`, `test:`, and `chore:` are encouraged.

By submitting a contribution, you agree that it may be distributed under the
MIT License in this repository.

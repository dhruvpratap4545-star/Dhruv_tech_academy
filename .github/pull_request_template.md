## What does this PR do?
<!-- One or two sentences. Link the PRD section, e.g. PRD §4.4 Forgot password -->

## Type
- [ ] feat  - [ ] fix  - [ ] refactor  - [ ] test  - [ ] docs  - [ ] chore  - [ ] security

## Checklist
- [ ] Matches the agreed spec (no unrequested features)
- [ ] Every protected route uses `require_permission`, tenant filter (`institute_id`) in place
- [ ] Migration included and reviewed (if models changed); `downgrade()` works
- [ ] Tests added: allowed + denied cases; all tests pass locally
- [ ] Lint/format clean (ruff, ESLint, Prettier)
- [ ] No secrets, `.env`, keys or real personal data committed
- [ ] `.env.example` updated for any new environment variable
- [ ] Security reviewed: authorization, tenant isolation, input validation, logging

## How to test
<!-- Steps a reviewer can follow -->

## Screenshots (UI changes)

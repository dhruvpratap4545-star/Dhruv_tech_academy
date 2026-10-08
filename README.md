# Dhruv Online Academy

Multi-tenant EdTech platform for schools, colleges and coaching institutes
([dhruvonlineacademy.com](https://dhruvonlineacademy.com)).

Built one milestone at a time on a shared core. The current milestone is
**M1 – Core Platform (authentication + authorization)**.

## Layout

| Folder | What it is |
|---|---|
| `backend/` | FastAPI + SQLAlchemy 2 (async) + PostgreSQL API. Modular monolith: `app/core/` for infrastructure, `app/modules/` for `auth`, `org`, `rbac`, `users`, `audit`, `notifications`. Milestone 1 is complete: 55 endpoints, 18 tables, 312 tests. |
| `frontend/` | React + Vite + TypeScript web app. |
| `legacy/` | The original site (19 HTML module pages and the Flask/FastAPI prototype). Design reference, still served by the current Render service. Frozen — see `legacy/README.md`. |
| `docs/` | PRDs (`specs/`), decision records, progress log, Render migration guide. |
| `.claude/` | Claude Code setup: skills, rules, agents, hooks, permissions. |

## Running it locally

Needs Python 3.12+, Node.js 22.13+, Git, and PostgreSQL 16/17 (Docker or native).

### 1. A database

Either Docker, which is what the compose file and CI describe:

```bash
docker compose up -d db db_test     # app on 5432, app_test on 5433
```

Or a native PostgreSQL install. Create the role and both databases once:

```sql
CREATE ROLE app LOGIN PASSWORD 'app' CREATEDB;
CREATE DATABASE app      OWNER app;
CREATE DATABASE app_test OWNER app;
```

Then point `DATABASE_URL` and `TEST_DATABASE_URL` in `backend/.env` at it. The test suite
reads `TEST_DATABASE_URL` from the environment and falls back to the compose port (5433).

### 2. Backend — http://localhost:8000 (API docs at `/docs`)

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate            # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt

copy .env.example .env            # Linux/macOS: cp .env.example .env
#   then fill in JWT_PRIVATE_KEY, JWT_PUBLIC_KEY and OTP_PEPPER — the file
#   has the exact commands for generating each one

alembic upgrade head
python -m app.core.seed           # roles, permissions, the Direct institute
uvicorn app.main:app --reload
```

Leaving `RESEND_API_KEY` blank is deliberate: with `ENVIRONMENT=local` the email body is
printed to the backend console instead of being sent, so OTP codes are readable during
development and no real inbox is ever touched. Outside `local` the code is never logged.

### First login

There is **no default password** — the seed creates the first Super Admin as `invited` with
no password, because default credentials and passwords in deploy logs are how platforms get
compromised. To get in the first time:

1. Set `SEED_SUPERADMIN_EMAIL` in `backend/.env` and run `python -m app.core.seed`.
2. Open the app, choose **Forgot your password**, and enter that address.
3. Read the 6-digit code from the backend console (or the real inbox once Resend is set up).
4. Set a password. The account activates and you can log in.

Everyone else arrives by invitation and follows the same idea with a setup code.

### 3. Frontend — http://localhost:5173

```bash
cd frontend
npm install
npm run dev
```

## Checks

```bash
cd backend  && ruff check . && ruff format --check . && pytest -q && pip-audit -r requirements.txt
cd frontend && npm run lint && npm run test -- --run && npm run build && npm audit
```

Backend tests come in two tiers. Unit tests need nothing and always run; integration tests
drive the real API against PostgreSQL and **skip** when no database is reachable — except in
CI, where a missing database fails the build instead of quietly passing.

Both suites run on every pull request via [GitHub Actions](.github/workflows/ci.yml).

## Deployment

Render, from [`render.yaml`](render.yaml): `dhruv-api` (web service),
`dhruv-web` (static site) and `dhruv-db` (PostgreSQL 16).

Nothing in `render.yaml` has been applied yet, and the file is written so that applying
it cannot disturb the site already running on the account. Read the comments in it before
the first `blueprint apply`: the database name, region and Postgres version are write-once,
and renaming the database later creates a new empty one rather than moving the old.

## Contributing

Work on a feature branch, never on `main`. The rules that are not negotiable:

- **Security first.** No secrets in code; parameterised queries only; validate every input;
  an authorization check on every protected route.
- **Multi-tenancy.** Every institute-scoped query filters by `institute_id`. A missing
  filter is a critical bug, not a style issue.
- **Authorization** goes through `require_permission("<resource>:<action>")`. Never compare
  role names inside route code.
- **No hard deletes** of users, institutes, branches or classes — archive or change status.
- **Every schema change is an Alembic migration**, with a working `downgrade()`. Never edit
  a migration that has already run.
- **Tests with every feature.** Anything touching auth or permissions needs an allowed case
  *and* a denied one.

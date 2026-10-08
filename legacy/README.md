# Legacy site (design reference)

The original Dhruv Academy site, moved here unchanged on 06-10-2026 when the repository
was restructured for the new platform. It is kept as a design reference and as the record
of what the live service currently runs.

| Item | What it is |
|---|---|
| `app.py` | Flask app: serves the 12 module pages from `templates/`, plus a Gemini proxy and an Exotel voice webhook. Most recent commits touched this file, so it is almost certainly what the live Render service runs. |
| `main.py` | An earlier FastAPI prototype with a SQLite admin panel, sub-admin permissions and token wallet. Superseded by the new `backend/`. |
| `routers/` | Router modules imported by `main.py`. |
| `templates/` | The 19 HTML pages (Library, Wallet, Coaching Hub, Kids Zone, Legal AI, Mobile Shield, …). **These are the design reference for the new React frontend.** |
| `static/` | Images, the promo video and the browser scripts those pages use. |

## Rules

- **Do not delete anything here.** These pages are the only record of the original designs.
- **Do not add features here.** All new work goes to `backend/` (FastAPI) and
  `frontend/` (React).
- Pages are ported into the React app one at a time, as their module's milestone starts.

## Running it locally

```bash
cd legacy
pip install -r requirements.txt
python app.py          # http://localhost:5000
```

Both files resolve paths relative to this folder, so always run them from inside
`legacy/`. On Render that means the service's **Root Directory must be `legacy`**.

## Known issues (not fixed — this code is frozen)

- `app.py` has no authentication on `/admin/super-master-panel`.
- `main.py` seeds an administrator with a hardcoded password, stores admin passwords in
  plain text, and uses SQLite on an ephemeral disk. That credential is in this repository's
  history; it should be rotated on the live service and the account retired, not migrated.
- `app.py` lists Gemini model names that do not exist (`gemini-3.5-pro`), so its fallback
  loop always falls through to the last option.

The new platform fixes these properly; nothing here should be copied forward as-is.

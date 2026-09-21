# Sri Balaji Granites & Marbles — Website

A two-sided web app for a natural-stone trading business (Bangalore yard,
Chittoor factory, Vishakapatnam export counter): a public digital catalog
customers browse and enquire from, plus a staff-only ERP for managing
stock, enquiries, announcements and reports across three yards.

Built to spec from the attached project report, using:
- **Backend:** Python Django (plain views, no DRF needed for this API's size)
- **Database:** Supabase (Postgres) via the Django ORM — falls back to a
  local SQLite file automatically if `DATABASE_URL` isn't set, so it runs
  out of the box while you set up Supabase.
- **Frontend:** plain HTML / CSS / JS (no build step), styled as a
  minimalist, image-led masonry gallery per the attached design reference —
  black-on-white chrome, the stone photography supplies all the color.

## What changed in this version

- **Flask → Django.** The whole backend has been rebuilt on Django
  (`backend_django/`); `backend/` and the Flask-specific `api/index.py` are
  gone. Every `/api/...` route the frontend calls is unchanged, so
  `frontend/js/api.js` didn't need new endpoints — just a small tweak (see
  below) to support real file uploads.
- **Slow loading, fixed at the source.** The previous version stored every
  slab photo as a base64 string directly inside the `imageUrl` column, so
  *every* `/api/slabs` list call (catalog grid, admin table, cart) shipped
  the full image bytes for every single slab inline in the JSON response.
  Slab photos are now real uploaded files (`Slab.image`, a Django
  `ImageField` under `backend_django/media/slabs/`), and the API just
  returns a lightweight URL the browser can cache and lazy-load like any
  normal `<img>` — the actual fix for the slow-feeling catalog and admin
  screens, not just a client-side compression band-aid.
- **Photo update, fixed.** Editing a slab's photo now uploads the file
  directly (multipart/form-data) instead of round-tripping a multi-megabyte
  base64 string through a plain text field and JSON body on every save.
  Uploading a new photo cleanly replaces and deletes the old file on the
  server. Editing a slab *without* touching its photo now correctly leaves
  the existing photo alone, instead of having to resend it every time.
  Staff can still paste an external image URL instead of uploading a file
  if they prefer (`sfImage` field, now optional).

## Project layout

```
backend_django/
  manage.py
  sbg/
    settings.py            Reads .env (same variable names as before)
    urls.py                  Frontend routes + /api/ include + /media/
    wsgi.py
  catalog/
    models.py               Slab / TrashItem / CustomerQuery / Announcement
    views.py                  All /api routes
    urls.py
    calc.py                    Area / rate / currency calculation engine
    auth.py                     Staff role resolution + JWT
    frontend_views.py            Serves the plain HTML/CSS/JS frontend
    management/commands/seed.py   python manage.py seed
  requirements.txt
  .env.example
  media/                    Uploaded slab photos land here (gitignored)
frontend/
  index.html              Public catalog (masonry grid)
  about.html               Company / yards page
  staff.html                 Staff login + ERP dashboard
  css/style.css
  js/{api,calc,catalog,admin}.js
```

## 1. Set up the database (Supabase)

1. Create a project at supabase.com.
2. In **Project Settings → Database → Connection string**, copy the URI.
3. You don't need to run any SQL by hand — `python manage.py migrate`
   creates all tables automatically. `backend/supabase_schema.sql` from the
   previous version is no longer needed; Django's migrations
   (`catalog/migrations/0001_initial.py`) are the source of truth now.

## 2. Configure environment variables

```bash
cd backend_django
cp .env.example .env
# then edit .env: paste your DATABASE_URL, set a real SECRET_KEY, etc.
```

## 3. Install & run the backend

```bash
cd backend_django
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate
python manage.py seed            # loads sample yards/slabs/announcements
python manage.py runserver       # runs on http://localhost:8000
```

Django serves the frontend too — once it's running, open
`http://localhost:8000` for the catalog, `http://localhost:8000/staff`
for the ERP login.

No separate frontend server or build step is needed; `frontend/js/api.js`
calls the API on the same origin.

## 4. Staff login

Any of the usernames below signs in with the matching role, using **any**
password from `STAFF_PASSWORDS` in your `.env` (defaults to
`Shayam@123`, `admin@123`, `pass123`, `g1@123`, `g2@123`, `g3@123`,
`123456`):

| Username(s) | Role | Sees |
|---|---|---|
| `admin`, `shayam`, `superadmin`, or anything unrecognized | Super Admin | All 3 yards |
| `manager_g1`, `bangalore`, `g1` | Manager | Bangalore Yard only |
| `manager_g2`, `chittoor`, `g2` | Manager | Chittoor Factory only |
| `manager_g3`, `vizag`, `g3` | Manager | Vishakapatnam Export only |

## Security — read before going live

This preserves the original prototype's shared/universal-password login
model (documented in the project report) so the app works immediately.
**Before real deployment**, replace it with per-user accounts and hashed
passwords — the report's Section 10.2 has the full checklist (real
authentication, moving uploaded photos to Supabase Storage / S3 for
durability, server-side validation, audit trail, real-time sync, backups).

Also replace the placeholder `picsum.photos` product images loaded by
`python manage.py seed` with real slab photography (uploaded through the
staff dashboard) before launch.

## Deploying

### Option A — Render / Railway / Fly.io / a VPS (recommended)

Any host that runs Django works. Example production start command:

```bash
python manage.py collectstatic --noinput
python manage.py migrate
gunicorn sbg.wsgi:application -w 4 -b 0.0.0.0:$PORT
```

(Root/start directory = `backend_django`.) Point `DATABASE_URL` at your
Supabase Postgres instance and set a strong `SECRET_KEY` and your own
`STAFF_PASSWORDS` in the host's environment variables (don't upload your
real `.env` file anywhere public). Make sure the host gives you a
**persistent disk** for `backend_django/media/` (uploaded slab photos) —
this is the one thing that matters more now than it did with the old
base64-in-the-database approach, since photos are real files on disk.

### Option B — Vercel

The repo includes `vercel.json` pointing at `backend_django/sbg/wsgi.py`.

1. Import the repo into Vercel (framework preset: "Other" — no build step
   needed).
2. In **Project Settings → Environment Variables**, add:
   - `DATABASE_URL` — your Supabase Postgres connection string
   - `SECRET_KEY` — a long random string
   - `STAFF_PASSWORDS` — your own comma-separated list
   - `CORS_ORIGINS` — your Vercel domain (or `*` while testing)
   - `WHATSAPP_NUMBER`, `WHATSAPP_NUMBER_SECONDARY` — optional
3. Deploy.

**Important caveat specific to this version:** Vercel's filesystem is
read-only/ephemeral outside `/tmp`, and `/tmp` is wiped on every cold
start. That was already true for the SQLite fallback DB — now it's also
true for uploaded slab photos (`backend_django/media/`), since they're
real files rather than base64 text inside the database row. On Vercel,
**always set `DATABASE_URL`** (never rely on the SQLite fallback), and
either accept that uploaded photos won't survive a cold start, or swap
`Slab.image`'s storage backend for Supabase Storage / S3 before relying on
photo uploads in production. Option A (a normal long-running server with a
persistent disk) avoids this entirely and is closer to how this app was
originally built.

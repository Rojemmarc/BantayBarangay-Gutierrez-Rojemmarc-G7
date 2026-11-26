# BantayBarangay

**BantayBarangay** is a barangay-level community concern and incident reporting platform built with Django, Django Templates, Leaflet maps, and PostgreSQL/Supabase. It connects residents, community volunteers, barangay officials, assigned field staff, and LGU analysts through role-based dashboards and an auditable report resolution workflow.

## Core Feature (Vertical Slice — Project Development 2)

**Community Incident & Concern Reporting Management** works end to end across the database, Django forms/views, URL routes, and server-rendered templates:

- **Create (`/app/new/`)**: Logged-in Residents and Volunteers submit a concern with category, title, description (minimum 20 characters), 1–3 JPG/PNG evidence photos (up to 5 MB each), optional landmark note, interactive Leaflet map pin / latitude & longitude coordinates, and optional anonymous suspicious-activity toggle (for Safety reports). Daily rate limit: 5 reports per user per 24 hours.
- **Read (`/app/`, `/official/`, `/lgu/`, `/reports/<id>/`)**: Role-scoped dashboards with search, category/status/date filters, pagination, emergency prioritization, map preview, photo gallery, status timeline (`StatusHistory`), and official/community updates (`Comment`).
- **Update (`/reports/<id>/edit/`, `/reports/<id>/transition/`, `/reports/<id>/comment/`, `/reports/<id>/rate/`)**:
  - Reporters can edit their own `Pending` reports (fields, coordinates, add/remove photos while retaining at least 1 photo).
  - Officials assign `Pending` reports to a barangay `Department` and active `Staff` member, update status transitions (`Pending → Assigned → In Progress → Resolved` or `Rejected` with mandatory reason comment), post official updates, and rate `Resolved` reports (1–5).
  - Staff update status and post official updates on reports assigned to them.
  - Volunteers post community coordination updates on active barangay reports.
- **Delete (`/reports/<id>/delete/`)**: Reporters can permanently delete their own `Pending` reports (locked once assigned or processed).

## Standard Features (Project Development 1)

- **Account Registration (`/register/`)**: Public sign-up with password strength validation, barangay selection, data privacy consent, and forced `Resident` role.
- **Login / Logout (`/login/`, `/logout/`)**: Email-based login with Argon2 password hashing, 5-attempt lockout protection, session timeout (30 min), and POST-only logout.
- **Role-Based User Dashboards**: Automatic redirect on login to `/app/` (Resident/Volunteer), `/official/` (Official/Staff), or `/lgu/` (LGU analytics).
- **User Profile (`/profile/`)**: Authenticated users can view their role and barangay and update their full name, email (with uniqueness validation), and contact number.

## Target Users & Role-Based Access

| Role | Dashboard Route | Core Feature Capabilities & Access Boundary |
|---|---|---|
| Resident | `/app/` | Create, view, edit, and delete own `Pending` reports; receive alerts; view bulletin & profile. Sees own reports only (max 5 submissions/day). |
| Volunteer | `/app/` | Submit, edit/delete own `Pending` reports; view local barangay reports (other reporters anonymized); post community updates on active cases. |
| Official | `/official/` | View all barangay reports & reporter contacts; assign Department + active Staff; transition status; post official updates; rate `Resolved` reports; manage bulletin announcements. |
| Staff | `/official/` | View assigned-report queue only; transition assigned reports (`Assigned → In Progress → Resolved`); post official updates; receive assignment alerts. |
| LGU | `/lgu/` | View cross-barangay aggregate totals by status, category, and barangay only (no report-level PII, photos, or exact coordinates). |
| Superuser / Admin | `/django-admin/` | Full system-level administration via Django Admin. |

## Local & PostgreSQL/Supabase Setup

### 1. Clone and create virtual environment

```powershell
git clone https://github.com/Rojemmarc/BantayBarangay-Gutierrez-Rojemmarc-G7.git
cd BantayBarangay-Gutierrez-Rojemmarc-G7
```

On Windows Command Prompt, you can run `setup.bat`, or manually via PowerShell:

```powershell
cd backend
py -3 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure environment variables (`.env`)

Copy `backend/.env.example` to `.env` (in either the project root or `backend/` — `.env` is excluded by `.gitignore`) and configure your PostgreSQL/Supabase database connection string:

```env
DEBUG=1
SECRET_KEY=replace-with-a-long-random-secret
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=postgresql://postgres.PROJECT_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres
DB_SSL=1
SSL_REDIRECT=0
```

> If `DATABASE_URL` is omitted locally while `DEBUG=1`, Django falls back to `backend/db.sqlite3`.

### 3. Run migrations, cache table, and demo seed

```powershell
cd backend
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py createcachetable
.\venv\Scripts\python.exe manage.py seed --demo
```

### 4. Start the development server

```powershell
.\venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Open `http://127.0.0.1:8000` (or run `run.bat` from the repository root).

### Demo Test Accounts (created by `manage.py seed --demo`)

All demo accounts belong to **Tisa, Cebu City** and use password **`DemoPass#2026x`** (never run `--demo` in production):

| Role | Email | Password |
|---|---|---|
| Resident | `resident@demo.ph` | `DemoPass#2026x` |
| Volunteer | `volunteer@demo.ph` | `DemoPass#2026x` |
| Official | `official@demo.ph` | `DemoPass#2026x` |
| Staff | `staff@demo.ph` | `DemoPass#2026x` |
| LGU | `lgu@demo.ph` | `DemoPass#2026x` |

### 5. Run automated tests

```powershell
cd backend
$env:DEBUG="1"
.\venv\Scripts\python.exe manage.py test
```

## Key Project Structure

```text
backend/
  bantay/          settings.py (.env + PostgreSQL/Supabase), urls.py, wsgi.py
  core/
    models.py      Barangay, User, Department, Category, Report, ReportPhoto, StatusHistory, Comment, Announcement, Notification
    forms.py       ReportForm, ReportTransitionForm, ReportCommentForm, ReportRatingForm, ProfileForm
    web.py         Server-rendered views & role-based access controls
    web_urls.py    URL routes for auth, dashboards, profile, and report CRUD
    migrations/    Schema and reference data migrations (0001–0004)
    management/    seed.py command for reference & demo data
  templates/       base.html, home.html, new_report.html, edit_report.html, detail.html, profile.html, lgu_dashboard.html, alerts.html, bulletin.html, auth/, partials/
  static/          css/app.css, js/app.js, js/theme.js, img/, vendor/leaflet/
docs/              Project Development completion report PDF
```

## Git Branching Strategy

- `main`: stable release branch only (updated via Pull Request from `develop`).
- `develop`: integration branch created from `main`.
- `feature/<feature-name>`: feature branches created from `develop` and merged back via Pull Requests (`feature/incident-reporting-crud`, `feature/role-workflow-and-seeding`, `feature/pd2-completion-report`).

# BantayBarangay

**BantayBarangay** is a barangay-level community concern and incident reporting platform built with Django, Django Templates, Leaflet maps, and PostgreSQL/Supabase. It connects residents, community volunteers, barangay officials, assigned field staff, and LGU analysts through a responsive public landing page, role-based workspaces, and an auditable report resolution workflow.

## Highlights & Latest Upgrades

### Backend Architecture, Security & Workflows
- **Shared Domain Services (`backend/core/services.py`)**: Centralized role access control (`scope_reports`, `reports_for_user`), dashboard stats, SQL-level barangay leaderboard ranking, emergency alerting, EXIF stripping, per-IP rate limiting, and formula-safe CSV escaping.
- **Privacy & Media Integrity**:
  - Automatic **EXIF metadata stripping** (camera model, timestamps, embedded GPS) via Pillow on every uploaded JPG/PNG photo.
  - Automatic **physical photo file cleanup** on `ReportPhoto` deletion (`post_delete` + `transaction.on_commit`) to prevent orphaned files on disk.
  - Safe `404` handling when media files are missing on disk, plus optional **S3 / Supabase Storage** backend support in `settings.py`.
- **Expanded Workflows & Exports**:
  - **Emergency Alerts for Officials**: Submitting an `Emergency` report automatically alerts active barangay Officials and unlocks `/app/alerts/` for Officials.
  - **Report Reassignment (`/reports/<id>/reassign/`)**: Officials can reassign active `Assigned` or `In Progress` reports to another Department and active Staff member with automatic notifications.
  - **Resolution Proof Photos (`is_resolution_proof`)**: Staff and Officials can attach up to 2 optional after/resolution proof photos when marking a report `Resolved`.
  - **In-App Password Change (`/profile/password/`)**: Authenticated users can update their password securely while keeping their session active.
  - **Complete Bulletin CRUD (`/bulletin/<id>/edit/`)**: Django `AnnouncementForm` supporting create, edit, delete, and optional `expires_at` scheduling.
  - **Formula-Safe CSV Exports**: Officials can export filtered barangay reports (`/official/export.csv`) and LGU analysts can export anonymized aggregate summaries (`/lgu/export.csv`).
- **Database Performance (`0005_report_indexes_and_resolution_photo`)**: Composite indexes for Staff queues (`assigned_to, status`) and Official emergency sorting (`barangay, is_emergency, status`).

### Frontend UI/UX, Landing Page & Accessibility
- **Public Landing Page (`/`)**: Full-width responsive civic landing page featuring a structured status lifecycle card, live non-PII platform metrics, 6 capability cards, 3-step workflow, 5-role overview, and light/dark mode support (authenticated users continue redirecting automatically to their role dashboards).
- **Cleaned Transparent Brand Logo**: De-fringed `bantaybarangay-logo.png` rendered across the header, auth/password-reset screens, favicon, and PWA `manifest.json`.
- **Profile Avatar Dropdown Menu & Responsive Bottom Navigator**: Compact circular avatar button in the top-right header opening a dropdown with **Profile**, **Dark mode** toggle (`On`/`Off`), and **Log out**; on smaller screens (`<= 860px`), primary navigation automatically docks as a fixed bottom navigator bar with icons across both the landing page and authenticated workspaces.
- **Lag-Aware Skeleton Loading**: Top loading progress bar (`#navProgress`) and automatic shimmering skeleton page shell (`#pageSkeleton`) when navigation takes longer than `180ms`, plus shimmering skeletons for report photos and Leaflet maps.
- **Standard UX & Responsive Layouts**:
  - Multi-column desktop layouts for Report Detail (main report + sticky timeline/actions sidebar), Bulletin (feed + ranked leaderboard), LGU Analytics (side-by-side progress bar charts), and Profile (details + security card).
  - Inline field-level validation (`aria-invalid="true"`), password show/hide toggles & strength indicator, live 20-char description counter, instant upload thumbnail previews, **"Use my current location"** GPS button, Official barangay-wide incident map, themed `<dialog>` confirmation modal & photo lightbox, skip-to-content link, `@media print` blotter layout, and GPU-accelerated scroll-reveal & count-up animations (`prefers-reduced-motion` safe).

## Core Feature (Vertical Slice — Project Development 2)

**Community Concern & Incident Reporting Management** works end to end across PostgreSQL/Supabase, Django models/migrations, Django forms/views, URL routes, and server-rendered templates:

- **Create (`/app/new/`)**: Residents and Volunteers submit concerns with category, title, description (≥ 20 chars), 1–3 EXIF-stripped JPG/PNG photos (≤ 5 MB each), optional landmark, Leaflet map / GPS coordinates, and optional anonymous Safety toggle (max 5 reports/day).
- **Read (`/app/`, `/official/`, `/lgu/`, `/reports/<id>/`)**: Role-scoped dashboards with quick status filter chips, search, collapsible category/date filters, Official active incident map, photo lightbox, status timeline (`StatusHistory`), and official/community updates (`Comment`).
- **Update (`/reports/<id>/edit/`, `/transition/`, `/reassign/`, `/comment/`, `/rate/`)**: Reporters edit own `Pending` reports; Officials assign/reassign Departments & Staff, transition statuses, post updates, and rate `Resolved` reports (1–5); Staff update progress & upload resolution proof; Volunteers coordinate on active cases.
- **Delete (`/reports/<id>/delete/`)**: Reporters delete own `Pending` reports with themed confirmation modal and automatic storage file cleanup.

## Standard Features (Project Development 1)

- **Account Registration (`/register/`)**: Public Resident sign-up with strong password checks, Argon2 hashing, barangay selection, and RA 10173 privacy consent.
- **Login / Logout (`/login/`, `/logout/`)**: Email-based login with per-email & per-IP lockout protection, 30-minute inactivity timeout, and POST-only logout.
- **Role-Based User Dashboards**: Automatic routing on login to `/app/` (Resident/Volunteer), `/official/` (Official/Staff), or `/lgu/` (LGU analytics).
- **User Profile & Security (`/profile/`, `/profile/password/`)**: View Role and Barangay, edit full name/email/contact number, and change password in-app.

## Target Users & Role-Based Access

| Role | Dashboard Route | Capabilities & Access Boundary |
|---|---|---|
| Resident | `/app/` | Create, view, edit, and delete own `Pending` reports; receive alerts; view bulletin & profile. Own reports only (max 5/day). |
| Volunteer | `/app/` | Submit, edit/delete own `Pending` reports; view local barangay reports (other reporters anonymized); post community updates on active cases. |
| Official | `/official/` | View all barangay reports, incident map & reporter contacts; assign/reassign Department & Staff; transition statuses; receive Emergency alerts; export CSV; rate `Resolved` reports; manage bulletin CRUD. |
| Staff | `/official/` | View assigned-report queue only; transition assigned cases (`Assigned → In Progress → Resolved`), attach resolution proof photos, post official updates, and receive alerts. |
| LGU | `/lgu/` | View cross-barangay aggregate totals & visual bars by status, category, and barangay + export anonymized CSV (zero PII). |
| Superuser / Admin | `/django-admin/` | Full system-level administration via Django Admin. |

## Local & PostgreSQL/Supabase Setup

### 1. Clone and create virtual environment

```powershell
git clone https://github.com/Rojemmarc/BantayBarangay-Gutierrez-Rojemmarc-G7.git
cd BantayBarangay-Gutierrez-Rojemmarc-G7
```

On Windows Command Prompt, run `setup.bat`, or manually via PowerShell:

```powershell
cd backend
py -3 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure environment variables (`.env`)

Copy `backend/.env.example` to `.env` (in either the project root or `backend/` — `.env` is excluded by `.gitignore`) and set your PostgreSQL/Supabase connection string:

```env
DEBUG=1
SECRET_KEY=replace-with-a-long-random-secret
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=postgresql://postgres.PROJECT_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres
DB_SSL=1
SSL_REDIRECT=0
```

> If `DATABASE_URL` is omitted locally while `DEBUG=1`, Django falls back to `backend/db.sqlite3`. Optional S3/Supabase Storage and SMTP settings are documented in `backend/.env.example`.

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

### Demo Test Accounts (`manage.py seed --demo`)

All demo accounts belong to **Tisa, Cebu City** and use password **`DemoPass#2026x`** (never run `--demo` in production):

| Role | Email | Password |
|---|---|---|
| Resident | `resident@demo.ph` | `DemoPass#2026x` |
| Volunteer | `volunteer@demo.ph` | `DemoPass#2026x` |
| Official | `official@demo.ph` | `DemoPass#2026x` |
| Staff | `staff@demo.ph` | `DemoPass#2026x` |
| LGU | `lgu@demo.ph` | `DemoPass#2026x` |

### 5. Run automated tests & CI

```powershell
cd backend
$env:DEBUG="1"
.\venv\Scripts\python.exe manage.py test
```

GitHub Actions (`.github/workflows/ci.yml`) automatically runs `manage.py check`, `makemigrations --check --dry-run`, `migrate`, `createcachetable`, and all **56 automated tests** against **PostgreSQL 16** on every push and Pull Request.

## Key Project Structure

```text
.github/workflows/ ci.yml (PostgreSQL 16 CI pipeline)
backend/
  bantay/          settings.py (.env, PostgreSQL/Supabase, optional S3 storage), urls.py, wsgi.py
  core/
    models.py      Domain models, DB check constraints, composite indexes, photo file cleanup signal
    services.py    Shared role scoping, SQL leaderboard, EXIF stripping, emergency alerts, rate limits, CSV safety
    forms.py       RegisterForm, ProfileForm, ReportForm, ReportTransitionForm, ReportReassignForm, ReportCommentForm, ReportRatingForm, AnnouncementForm
    web.py         Server-rendered views, role access controls, CSV exports, pagination
    web_urls.py    URL routes for landing, auth, dashboards, profile, password, reports, bulletin, exports
    migrations/    Schema and seed migrations (0001–0005)
    management/    seed.py command for reference & demo data
    tests*.py      56 automated tests (API, Web CRUD, Seeding, Security, UX & Skeleton Loading)
  templates/       base.html, landing.html, home.html, new_report.html, edit_report.html, detail.html, profile.html, change_password.html, lgu_dashboard.html, alerts.html, bulletin.html, edit_announcement.html, auth/, partials/
  static/          css/app.css, js/app.js, js/theme.js, manifest.json, img/, vendor/leaflet/
docs/
  BantayBarangay-Gutierrez-Rojemmarc-G7-PD2.pdf   Project Development 2 completion report
  BantayBarangay-Updates-Documentation.pdf        Backend, Frontend UX, Landing Page & CI updates documentation
```

## Git Branching Strategy

- `main`: stable release branch only (updated via Pull Requests).
- `develop`: integration branch created from `main`.
- `feature/<feature-name>`: dedicated feature branches (`feature/incident-reporting-crud`, `feature/role-workflow-and-seeding`, `feature/pd2-completion-report`, `feature/clean-brand-logo`, `feature/pro-backend-and-ux-standards`).

# CareConnect AI

CareConnect AI is a portfolio demonstration of a healthcare management platform. All seeded profiles, accounts, availability, and generated ML records are fictional. It is not a certified medical product and is not a substitute for professional medical care.

## What's implemented

- Responsive React/Vite application with public home, doctor directory and profiles, registration/login, patient dashboard, appointments, document library, and care team model insights.
- FastAPI + SQLAlchemy + SQLite API with bcrypt password hashes, JWT sessions, role checks, appointment slot validation, document ownership checks, private in-app notifications, consultation notes, and admin management.
- PDF validation and local text extraction with PyMuPDF; textless/scanned documents are identified as requiring OCR.
- Patient-only AI Health Report Analyzer for text-based lab PDFs: local rule-based value candidates, report excerpts, bounded report-specific chat retrieval, and optional localhost Ollama. It does not diagnose or claim clinical validation.
- Reproducible synthetic no-show model training and evaluation. Its scores measure only the synthetic data generator and are not evidence of real-world accuracy.
- API docs at `http://localhost:8000/docs` when running locally.

Patients can view notes from their own consultations; only the assigned doctor can create or edit them. Notifications stay private to the account. Admins can create fictional doctor profiles, activate or deactivate users, and update appointment statuses. This is a local portfolio demo, not a production deployment. Review `docs/architecture.md`, `docs/model_card.md`, and `docs/api.md` for scope and limitations.

## Windows setup (PowerShell)

Open two PowerShell terminals in the project root.

### Backend

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
Copy-Item .env.example .env
$env:JWT_SECRET = "replace-this-with-a-long-random-local-secret"
python backend\scripts\seed_demo_data.py
python backend\scripts\train_no_show_model.py
uvicorn app.main:app --app-dir backend --reload
```

The API defaults to SQLite at `backend/careconnect.db`. The model is optional; the API reports model unavailable until it is trained. Uploads and model artifacts are local and ignored by Git.

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Set `$env:VITE_API_URL` before `npm run dev` to use a different API URL. The backend CORS allowlist defaults to `http://localhost:5173`; configure `FRONTEND_ORIGINS` as a comma-separated list when needed.

For local testing, copy `frontend\.env.example` to `frontend\.env.local` (or use the provided ignored local file) and set `VITE_API_URL=http://localhost:8000/api/v1`. The value must include `/api/v1`; the frontend appends paths such as `/appointments`. Start FastAPI with `uvicorn app.main:app --app-dir backend --reload` so it listens at `http://localhost:8000`, then restart Vite after changing env files. Vite does not automatically load `.env.example`. Production uses the Vercel frontend environment variable `VITE_API_URL=/api/v1`; there is no production localhost fallback.

### Coordinated Vercel and Supabase deployment

The repository-root `vercel.json` defines one Vercel Services project with the Vite frontend and FastAPI API as separate services. The API entrypoint is `backend/main.py`; the API service installs `backend/requirements.txt`. `/api/*` is routed to FastAPI before the frontend catch-all. The frontend uses `VITE_API_URL` at build time; set it to `/api/v1` for same-origin production routing. `frontend/vercel.json` provides SPA history-route fallback. Vercel Services is currently a beta feature; confirm it is enabled for your account before choosing this single-project layout. If unavailable, deploy two Vercel projects from the `frontend/` and `backend/` roots and set the frontend `VITE_API_URL` to the backend's HTTPS `/api/v1` URL. Set the backend `FRONTEND_ORIGINS` to the exact frontend production origin. Use Vercel Hobby only for a personal, non-commercial portfolio demo; plan limits and Services availability can change.

Create a **new, empty** Supabase Free project. Do not point it at local SQLite data or import local databases, uploads, reports, or user records. The app creates its SQLAlchemy tables on initial API startup with `Base.metadata.create_all`; this creates missing tables but does not migrate existing schemas. Start with an empty database and do not run the fictional demo seed script against production. After the first patient account is registered, use the Supabase SQL Editor to promote only that account to administrator, then create fictional clinician profiles from the admin screen:

```sql
UPDATE users SET role = 'admin'
WHERE lower(email) = lower('<your-admin-account-email>') AND role = 'patient';
```

Configure these Vercel environment variables for the API service (set environment scope to Production, and Preview only if using an isolated test database):

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | Supabase **Transaction pooler** URI on port `6543`, copied from Connect; use its exact pooler username/host and database password. The API enforces SSL and disables prepared statements. |
| `JWT_SECRET` | A randomly generated secret of at least 32 characters; never commit it. |
| `TOKEN_MINUTES` | Optional; defaults to `60`. |
| `MAX_UPLOAD_BYTES` | `4194304` (4 MiB). |
| `MAX_REPORT_BYTES` | `4194304` (4 MiB). |
| `SUPABASE_URL` | Project URL from Supabase Project Settings → API. Server-side only. |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-only secret key from Supabase API settings. Never set a `VITE_` prefix or expose it to the browser. |
| `SUPABASE_STORAGE_BUCKET` | `private-health-reports` (must be created as a private bucket; API stores both document-library PDFs and analyzer PDFs here). |
| `FRONTEND_ORIGINS` | Optional comma-separated exact HTTPS Vercel production/preview origins or custom frontend domain. Vercel deployment, branch, and production URLs are also allowlisted from its system variables. No wildcard is accepted. |

Configure these for the frontend service at build time:

| Variable | Value |
| --- | --- |
| `VITE_API_URL` | `/api/v1` |
| `VITE_MAX_UPLOAD_BYTES` | `4194304` |

The frontend's local `.env.example` keeps the local API URL and 10 MiB local limit. Vercel overrides those at build time. SQLite remains the local default; production Vercel startup refuses to run without a PostgreSQL URL and a strong JWT secret. Use Supabase's transaction pooler, as Vercel functions are serverless and open short-lived connections. Table creation is automatic on cold start; there is no destructive migration or production demo seeding.

**Upload limit and persistence:** Vercel Functions reject request bodies over 4.5 MB, so both PDF upload routes are capped at 4 MiB. Local uploads stay at 10 MiB. The API validates the authenticated patient, PDF content, and size, then sends the original to the configured Supabase Storage bucket using a server-only service key. The bucket must be private; no public URLs or client-side service keys are used. Extracted report text, analysis, and chat remain in PostgreSQL under the authenticated owner. The old document library retains its extracted text and metadata in PostgreSQL. Configure the private bucket's allowed MIME type as `application/pdf` and maximum size as `4194304` bytes. Supabase Storage Free currently includes 1 GB, with a 50 MB per-file maximum; the app's Vercel body limit is lower. Do not upload real patient data to this portfolio demo. Generated model artifacts and local database/upload files are excluded from the backend deployment bundle. Therefore the no-show model endpoint remains unavailable on Vercel unless a separately reviewed model packaging strategy is added; the local model and training workflow remain unchanged.

Supabase Free currently has a 500 MB database quota and may pause projects after a week of low activity; resume them from the dashboard. Treat this as a portfolio deployment, not a production medical-record system: use fictional data only, and do not claim legal or clinical compliance.

#### Manual deployment steps

1. Push the project to your own GitHub repository after reviewing ignored files and removing any sensitive local data from Git history. This setup does not import local SQLite or documents.
2. Create a new Supabase Free project and copy its Transaction pooler connection URI from **Connect**. Keep the database password private.
3. Create a Vercel project from the repository root (not `frontend/` or `backend/`) so root `vercel.json` can build both services. Confirm the account supports Vercel Services and use Hobby only for personal non-commercial use.
4. In Supabase Storage, create a bucket named `private-health-reports`, keep it private, and restrict it to `application/pdf` and `4194304` bytes. Do not create a public bucket or client access policy for this server-managed bucket.
5. Set the API environment variables above in Vercel. Set `DATABASE_URL` to the pooler URI with port `6543`; set strong `JWT_SECRET`; set `SUPABASE_URL`, the server-only `SUPABASE_SERVICE_ROLE_KEY`, and `SUPABASE_STORAGE_BUCKET=private-health-reports`; limit both backend upload settings to `4194304`.
6. Set frontend build variables `VITE_API_URL=/api/v1` and `VITE_MAX_UPLOAD_BYTES=4194304`. Add exact preview/custom origins to `FRONTEND_ORIGINS` if needed. With separate Vercel projects, use the backend HTTPS origin in `VITE_API_URL` and the frontend HTTPS origin in `FRONTEND_ORIGINS`.
7. Deploy from the Vercel dashboard or your own terminal. This repository preparation does not deploy or create resources.
8. Visit `/api/v1/health`, `/docs`, and a client route such as `/health-reports`; register an account and check patient authorization. Then promote your chosen account to admin with the SQL statement above. Test PDF uploads only with fictional PDFs under 4 MiB, then verify they appear in the private Storage bucket.
9. Confirm the Supabase project stays within its quota and has not paused. Configure a separate Preview database/bucket if enabling Vercel preview deployments; avoid using production records in previews.

### AI Health Report Analyzer

Patients can open **AI report analyzer** from the account menu or dashboard. Upload a text-based laboratory PDF up to 10 MB (configurable with `MAX_REPORT_BYTES`). PyMuPDF extracts selectable text locally; scanned image PDFs need OCR, which is not bundled. Transparent line rules identify possible values and compare them only with a numeric range found on that same line. Check every candidate against the PDF. The report chat retrieves snippets from the selected report only; its default keyword-retrieval mode does not provide generated clinical interpretation. It says when it cannot find requested information. Each patient can access only their own reports. Admin and doctor roles do not get report access. Deleting a report also deletes its analysis and report chat.

The default mode is `Local rules and retrieval`, works without an external service, API key, model download, or GPU. An optional separately installed Ollama service can be enabled for generated answers by setting `OLLAMA_MODEL` to an already installed model and keeping `OLLAMA_BASE_URL` on localhost (default `http://127.0.0.1:11434`). The app checks availability and falls back to local retrieval if unavailable. Report text is never sent to a cloud AI provider. Local model output is not clinically validated; review it with a healthcare professional.

For local development, report data is stored in the SQLite database and generated-name files under `backend/report_uploads`; those files are outside the frontend and ignored by Git. In Vercel, original PDFs are stored in the private Supabase bucket and extracted text, analysis, and chat are stored in PostgreSQL. Deleting a document or report removes its stored PDF through the Storage API. No automatic retention limit is implemented. This portfolio app has not had a legal or technical privacy compliance review.

### Demo sign-ins

Run the seed command to create these fictional users. The shared password is `DemoPass123!`.

- Patient: `patient@careconnect.demo`
- Administrator: `admin@careconnect.demo`
- Doctors: each seeded doctor's name is converted to a dotted email, such as `maya.chen@careconnect.demo`.

Registration creates patient accounts only. Doctor and administrator accounts are seeded for the local demo.

### Checks

```powershell
python -m pytest backend\tests -q
cd frontend
npm run build
```

Run the test command from the activated backend virtual environment. The frontend build runs from `frontend` after `npm install`.

## Data model

`User` has a unique email and a patient/doctor/admin role. `Doctor` extends a doctor-role user and links to one `Specialty`; `Availability` defines unique doctor/date/hour slots. `Appointment` links one patient to one doctor and enforces uniqueness among active doctor/time bookings. `ConsultationNote` is scoped to one appointment and its assigned patient and doctor. `Notification` belongs to one user and may link to an appointment. `Document` belongs to an owner and stores extracted text plus a server-generated filename. Passwords are never returned from APIs. See [the schema notes](docs/architecture.md).

## Medical document notes

PDFs are capped at 10 MB and checked by extension, MIME type, and PDF magic bytes. Documents are stored locally under a generated filename, tied to the authenticated patient, and can be deleted. Text extraction is not OCR. The simple summary reports terms and date strings explicitly found in extracted text; it does not diagnose or recommend treatment.

## Portfolio deliverables

- [Architecture and schema](docs/architecture.md)
- [API outline](docs/api.md)
- [ML model card and evaluation caveats](docs/model_card.md)
- [Demo script](docs/demo-script.md)

Screenshots should be captured after running the app in the intended browser environment. See the verification record below for the actual commands run here.

## Verification record (Windows environment, 2026-10-27)

- `npm install --ignore-scripts --cache ..\..\..\work\npm-cache --no-audit --no-fund` completed successfully. `npm ls --depth=0` verified all eight declared direct dependencies at their declared versions.
- `npm run build` was attempted twice, including with `ESBUILD_BINARY_PATH` set to the installed Windows executable. Both attempts stopped while Vite bundled `vite.config.js`: `Error: spawn EPERM` from `esbuild/lib/main.js` (`ensureServiceIsRunning`). This is a child-process restriction in this environment. A direct esbuild JavaScript/JSX bundle check succeeded (`217.5kb`), but it externalized CSS and is not a Vite production build. On a normal Windows terminal, rerun `cd frontend; npm run build`.
- `python -m pip install -r backend\requirements.txt` completed in the project `.venv`. Initial tests exposed a Passlib 1.7.4 incompatibility with bcrypt 5.0.0; `bcrypt==4.0.1` is now pinned and the environment was reinstalled.
- `.venv\Scripts\python.exe backend\scripts\train_no_show_model.py` succeeded using scikit-learn 1.6.1 and recorded both the logistic-regression model and `DummyClassifier` baseline.
- Baseline before the analyzer: `.venv\Scripts\python.exe -m pytest backend\tests -q` completed with **9 passed**, 6 dependency deprecation warnings.
- After the analyzer and predeployment updates: `.venv\Scripts\python.exe -m pytest backend\tests -q` completed with **24 passed**, 6 dependency deprecation warnings, no failures. This includes mocked checks that production PDF storage uses the server-side credential, rejects unsafe object keys, and calls the Storage removal API; it does not verify a live Supabase project.
- `npm.cmd run build` was run after integration and remains blocked before Vite can compile the app: `Error: spawn EPERM` from esbuild while bundling `vite.config.js`. JSX parsing succeeded for `src/main.jsx` and `src/HealthReportAnalyzer.jsx`, and Tailwind's direct CSS compiler produced 59,021 characters; neither check substitutes for the Vite production build. Rerun `cd frontend; npm.cmd run build` in a normal Windows terminal where Node child processes may start.
- Ollama was not configured or tested. The no-Ollama local retrieval path was covered by the backend tests.
- Deployment configuration check: Python `compileall`, JSX parsing, Vercel JSON routing/entrypoint checks, and Tailwind CSS compilation succeeded. `psycopg[binary]==3.3.6` could not be installed in this local environment because pip returned `ERROR: Could not find a version that satisfies the requirement psycopg==3.3.6 (from versions: none)`; Vercel/PostgreSQL connectivity therefore remains unverified here.
- `python -m compileall -q backend\app backend\scripts backend\tests` completed successfully earlier in this work session; the final pytest run imports the updated backend modules.
- Deployment preparation (2026-10-27): `.venv\Scripts\python.exe -m pytest backend\tests -q` completed with **24 passed**. `python -m compileall -q backend\app backend\tests` and `git diff --check` succeeded. `npm.cmd run build` was attempted and remains blocked before source compilation by `Error: spawn EPERM` from esbuild starting its child process. The Supabase Storage integration was tested with mocked HTTP only; no Supabase or Vercel deployment was created or tested.

The synthetic model scores describe only its generated data. They are not clinical evidence or real-world accuracy claims.

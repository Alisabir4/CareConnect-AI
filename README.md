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

The frontend API base defaults to `http://localhost:8000/api/v1`, matching the local backend URL. To override it through Vite, copy `frontend\.env.example` to `frontend\.env` and edit `VITE_API_URL`.

### AI Health Report Analyzer

Patients can open **AI report analyzer** from the account menu or dashboard. Upload a text-based laboratory PDF up to 10 MB (configurable with `MAX_REPORT_BYTES`). PyMuPDF extracts selectable text locally; scanned image PDFs need OCR, which is not bundled. Transparent line rules identify possible values and compare them only with a numeric range found on that same line. Check every candidate against the PDF. The report chat retrieves snippets from the selected report only; its default keyword-retrieval mode does not provide generated clinical interpretation. It says when it cannot find requested information. Each patient can access only their own reports. Admin and doctor roles do not get report access. Deleting a report also deletes its analysis and report chat.

The default mode is `Local rules and retrieval`, works without an external service, API key, model download, or GPU. An optional separately installed Ollama service can be enabled for generated answers by setting `OLLAMA_MODEL` to an already installed model and keeping `OLLAMA_BASE_URL` on localhost (default `http://127.0.0.1:11434`). The app checks availability and falls back to local retrieval if unavailable. Report text is never sent to a cloud AI provider. Local model output is not clinically validated; review it with a healthcare professional.

Reports are private health information saved in the local SQLite database and generated-name files under `backend/report_uploads`; they are not served from the frontend. No automatic retention limit is implemented. Delete reports in the UI to remove the file, extracted text, analysis and chat. This portfolio app has not had a legal or technical privacy compliance review.

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
- After the analyzer: `.venv\Scripts\python.exe -m pytest backend\tests -q` completed with **16 passed**, 6 dependency deprecation warnings, no failures.
- `npm.cmd run build` was run after integration and remains blocked before Vite can compile the app: `Error: spawn EPERM` from esbuild while bundling `vite.config.js`. JSX parsing succeeded for `src/main.jsx` and `src/HealthReportAnalyzer.jsx`, and Tailwind's direct CSS compiler produced 59,021 characters; neither check substitutes for the Vite production build. Rerun `cd frontend; npm.cmd run build` in a normal Windows terminal where Node child processes may start.
- Ollama was not configured or tested. The no-Ollama local retrieval path was covered by the backend tests.
- `python -m compileall -q backend\app backend\scripts backend\tests` completed successfully earlier in this work session; the final pytest run imports the updated backend modules.

The synthetic model scores describe only its generated data. They are not clinical evidence or real-world accuracy claims.

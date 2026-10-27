# API outline

Interactive OpenAPI documentation is exposed by FastAPI at `/docs`.

| Area | Implemented routes |
|---|---|
| Auth | `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `GET /api/v1/auth/me` |
| Directory | `GET /api/v1/doctors`, `GET /api/v1/doctors/{id}`, `GET /api/v1/doctors/{id}/availability`, `GET /api/v1/specialties` |
| Appointments | `POST /api/v1/appointments`, `GET /api/v1/appointments`, `PATCH /api/v1/appointments/{id}/status`, `PATCH /api/v1/appointments/{id}/reschedule`, `GET /api/v1/appointments/{id}/notes`, `PUT /api/v1/appointments/{id}/notes` |
| Patient | `GET /api/v1/patients/me`, `GET /api/v1/patients/me/appointments` |
| Documents | `POST /api/v1/documents`, `GET /api/v1/documents`, `POST /api/v1/documents/{id}/analyze`, `DELETE /api/v1/documents/{id}` |
| AI health reports (patient only) | `POST /api/v1/reports/upload`, `GET /api/v1/reports`, `GET /api/v1/reports/{id}`, `GET /api/v1/reports/{id}/analysis`, `POST /api/v1/reports/{id}/analyze`, `GET/POST/DELETE /api/v1/reports/{id}/chat`, `DELETE /api/v1/reports/{id}`, `GET /api/v1/reports/provider` |
| Notifications | `GET /api/v1/notifications`, `PATCH /api/v1/notifications/{id}/read` |
| Doctor | `GET /api/v1/doctor/me/appointments`, `POST /api/v1/doctor/me/availability` |
| ML | `POST /api/v1/ml/no-show/predict`, `GET /api/v1/ml/metrics` |
| Admin | `GET /api/v1/admin/overview`, `GET /api/v1/admin/users`, `GET /api/v1/admin/appointments`, `POST /api/v1/admin/doctors`, `PATCH /api/v1/admin/users/{id}/status` |

Login returns a bearer JWT. Registration is patient-only; demo doctors and the admin are provisioned by the seed script. Rescheduling retains the assigned doctor and reopens a pending request after verifying availability. Consultation notes are limited to the appointment's assigned doctor and patient. Notification lists and read operations are restricted to their owner. Admin routes support doctor account/profile creation, user activation, and appointment status management; the admin API does not return password hashes or consultation notes.

The report upload endpoint accepts `multipart/form-data` with a `file` field and requires a PDF extension, `application/pdf` content type, PDF signature, readable unencrypted pages and selectable text. Maximum bytes are controlled by `MAX_REPORT_BYTES` (default 10 MiB); extraction is capped at 250 pages and 250,000 characters. Report chat accepts JSON `{ "question": "..." }`. Report endpoints are patient-only and filter every lookup by the authenticated owner; doctors and admins do not inherit access. Delete removes the report, extracted text, structured analysis, conversation, and stored local file. OpenAPI at `/docs` contains the request/response schemas and route descriptions. Only fictional example values should be used in tests and examples.

The optional local provider status endpoint reports whether configured localhost Ollama is available. Without it, Q&A uses bounded keyword matching over snippets from the selected report and explicitly returns a limitation when nothing relevant is found. No remote model, external medical source, or cloud API is called.

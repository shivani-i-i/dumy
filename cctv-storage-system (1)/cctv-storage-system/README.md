# ICSLOS — Intelligent CCTV Storage Lifecycle and Optimization System

A rule-based, explainable Information Lifecycle Management (ILM) console for multi-camera CCTV storage.
Stack: **Python · Streamlit · PostgreSQL · pandas/numpy · Plotly · bcrypt**.

It manages *footage metadata* (no real video) and simulates the storage around it: capacity planning, RAID,
Hot/Warm/Cold tiering, incident-aware retention, backup with RPO/RTO, forecasting, alerts and audit logging.
The engine is **rule-based, not AI**; forecasting is **linear regression**, not AI.

## 1. Setup

```bash
python -m venv venv && source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # edit DB password if you like
```

Create the database (psql as the postgres superuser):

```sql
CREATE USER cctv_admin WITH PASSWORD 'change_me';
CREATE DATABASE cctv_storage OWNER cctv_admin;
```

Create tables + seed data, then start the app:

```bash
python -m database.init_db --demo      # --reset drops everything first; --demo loads the 10 demo cameras
streamlit run frontend/app.py
```

| User | Password | Role |
|---|---|---|
| admin | Admin@123 | Admin |
| manager | Manager@123 | Storage Manager |
| viewer | Viewer@123 | Viewer |

**Change these passwords** (Settings → Users) before showing anything outside class.

## 2. Tests

```bash
pytest                # or:  python run_tests.py   (no pytest needed)
```
39 tests cover capacity maths, compression, RAID, lifecycle rules (boundaries, priority, pressure, protection,
idempotency), retention classes, forecasting, backup RPO/RTO, alert thresholds and an end-to-end demo model.

## 3. Project structure

```
cctv-storage-system/
├── frontend/                  # everything the user sees (Streamlit)
│   ├── app.py                 #   entry point: login gate + role-based navigation
│   ├── views/                 #   the 12 sidebar pages
│   └── components/            #   charts + UI helpers
├── backend/                   # all business logic (no Streamlit imports except auth/session.py)
│   ├── auth/                  #   bcrypt hashing, login/lockout/timeout, role→permission map
│   ├── engines/               #   pure logic: capacity, compression, raid, retention, lifecycle, backup, forecast, alert
│   ├── services/              #   orchestration: RBAC re-check + SQL + audit (camera, footage, storage, raid, backup, ...)
│   ├── config/                #   env settings, reference tables, default settings
│   └── tests/                 #   pytest suite (39 tests)
├── database/                  # PostgreSQL layer
│   ├── schema.sql             #   15 tables, constraints, indexes, evidence-protection trigger
│   ├── init_db.py             #   create schema + seed (roles, users, pool, tiers, policy, RAID, settings)
│   └── connection.py          #   connection pool + query helpers
├── docs/                      # ER diagram, demo script, report material
├── requirements.txt  .env.example  pytest.ini  run_tests.py  README.md
```

```
Browser → frontend (login/session/RBAC guard → views) → backend/services (RBAC re-check, audit)
        → backend/engines (pure decisions) → database (PostgreSQL)
```
* `backend/engines` never import Streamlit or touch the DB → easy to unit-test and explain.
* Every mutating service re-checks the role; the UI is never trusted.
* `frontend/app.py` adds the project root to `sys.path`, so always launch from the project root:
  `streamlit run frontend/app.py`.
* The database has a trigger that refuses to hard-delete Incident / Critical Evidence / legal-hold footage.

## 4. Design decisions worth knowing (also good viva answers)

* **Lifecycle is deterministic and idempotent.** Pressure uses *pool* utilization (unchanged by tier moves), tiers only
  move *down* automatically, and re-running produces no further changes.
* **Protected footage** (Incident, Critical Evidence, legal hold) is never auto-deleted, stays Hot/Warm (restored from Cold
  if needed). Past its retention it raises a *review* alert instead of being deleted. Only an Admin can downgrade it.
* **Viewers** cannot change retention; they send a *request* (an alert) that Manager/Admin act on.
* **Deletion is two-step**: engine *marks*, then "Delete expired" soft-deletes (metadata kept, space freed).
* **Dry run vs Apply** on the lifecycle page, plus a *what-if utilization* slider.
* **Backups** cover Hot + Warm (Cold is already an archive). Recovery point = start time of the newest good backup.
* **Alert timestamps use the simulation clock**; the audit log uses real time.
* Alerts auto-resolve when the condition clears; a manually resolved alert reappears if the condition persists.
* Sizing uses assumptions (base bitrate per resolution, codec factors, linear FPS scaling). They are editable in Settings and
  must be described as assumptions in the report.

## 5. Honest limitations

* No real video is stored, encoded or restored; RAID/backup/compression are simulations.
* Single storage pool, single retention policy.
* Streamlit session state is per-browser-tab server memory (not JWT/cookies).
* Costs are relative units per TB-month, not currency.

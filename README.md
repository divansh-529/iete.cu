# IETE Student Forum ERP

Management and event operations platform for IETE Student Forum, Chandigarh University, based on the *Project Requirements & Development Blueprint v3.0*.

**Status:** Phases 1 (Foundation) and 2 (Organisation) are built and tested.
- **Phase 1:** sign-in, admin-created accounts, permissions and the audit log.
- **Phase 2:** departments, positions, reporting lines, the org chart, member profiles, and access tied to a position or department.

See [docs/06-roadmap.md](docs/06-roadmap.md) for the phases that follow.

The deployed website has no AI features of any kind (blueprint §16).

## Stack

| Layer | Choice |
|---|---|
| Frontend | React + Vite + TypeScript + Tailwind CSS, TanStack Query, React Router |
| Backend | Python + FastAPI, SQLAlchemy 2, Alembic, Pydantic v2 |
| Database | PostgreSQL 17 (Docker locally) |
| Auth | Custom: Argon2id hashing, server-side sessions in httpOnly cookies, CSRF tokens |

## Running it locally

You need Docker Desktop (running), Python 3.12+ and Node 20+.

```powershell
# 1. Database (from the project root)
docker compose up -d

# 2. Backend (first time only: create the venv and install)
cd backend
py -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\alembic upgrade head
.venv\Scripts\python -m app.cli create-superadmin --email you@example.com --name "Your Name"
.venv\Scripts\python -m app.cli seed-roles
.venv\Scripts\python -m app.cli seed-org

# 2b. Backend (every time)
.venv\Scripts\uvicorn app.main:app --reload --port 8000

# 3. Frontend (new terminal; first time: npm install)
cd frontend
npm run dev
```

Open http://localhost:5173 and sign in with the Chairperson account. The API docs are at http://localhost:5173/api/docs.

### Tests

```powershell
cd backend
.venv\Scripts\python -m pytest     # uses the iete_test database in the same Docker container
cd ..\frontend
npm run build                      # type-check + production build
```

### Going live

Free hosting on your own domain (Cloudflare Pages + Render + Neon): step-by-step in [docs/09-deployment.md](docs/09-deployment.md).

### Admin commands

| Command | Purpose |
|---|---|
| `python -m app.cli create-superadmin --email … --name …` | Create the Chairperson account (only once; prompts for the password) |
| `python -m app.cli seed-roles` | Create the default Leadership / Department Lead / Member roles |
| `python -m app.cli seed-org` | Create the leadership positions and the 9 departments from the blueprint, with their default access (empty organisation only) |
| `python -m app.cli sync-defaults` | After an upgrade: add new default role permissions and grants to an existing installation (never removes) |
| `python -m app.cli expire-grants` | Mark lapsed grants and log them (schedule nightly) |

## Repository layout

```
backend/   FastAPI app (app/<module>/{models,schemas,service,router}.py), Alembic migrations, tests
frontend/  React SPA (src/features/<module>/…)
docs/      Design documents, read in numbered order
```

## Design documents

1. [01-architecture.md](docs/01-architecture.md): system shape, request flow, auth
2. [02-permissions.md](docs/02-permissions.md): roles, scoped grants, the access check, audit
3. [03-data-model.md](docs/03-data-model.md): entities, relationships, invariants
4. [04-schema.sql](docs/04-schema.sql): full PostgreSQL schema draft for all phases
5. [05-api-outline.md](docs/05-api-outline.md): REST endpoints and the permission each requires
6. [06-roadmap.md](docs/06-roadmap.md): Phases 0–8 with exit criteria
7. [07-open-decisions.md](docs/07-open-decisions.md): decisions to confirm, each with a recommended default
8. [08-free-tier-hosting.md](docs/08-free-tier-hosting.md): hosting, storage, backups

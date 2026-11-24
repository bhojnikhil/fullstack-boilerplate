# {{APP_NAME}} - Full-Stack Boilerplate Context

This document provides context for AI-assisted development on this full-stack boilerplate.

> **Read the "Known issues" warning in README.md first.** The current auth and data-access
> code has known security and design defects that are being fixed in the v2 upgrade.

## Architecture Overview

This is a 3-tier full-stack application:

```
Frontend (Next.js 15, React 19)
    ↓ (axios API calls)
Backend (FastAPI + SQLAlchemy)
    ↓ (SQL)
Database (PostgreSQL)
```

### 3-Layer Backend Pattern

1. **Router Layer** (`app/routers/`): HTTP endpoints, request/response handling
2. **Service Layer** (`app/services/`): Business logic, orchestration
3. **Repository Layer** (`app/repositories/`): Database access only

This ensures clean separation of concerns and testability.

## Project Structure

```
fullstack-boilerplate/
├── apps/
│   ├── api/                         # FastAPI service (uv)
│   │   ├── app/
│   │   │   ├── main.py              # FastAPI app initialization
│   │   │   ├── auth/                # security.py (hashing, JWT), dependencies.py
│   │   │   ├── core/                # config.py (settings), db.py (engine, SessionLocal, get_db)
│   │   │   ├── models/              # base.py, user.py (User, OAuthAccount), item.py, enums.py
│   │   │   ├── schemas/             # Pydantic request/response models
│   │   │   ├── repositories/        # UserRepository, OAuthAccountRepository, ItemRepository
│   │   │   ├── services/            # AuthService (no password reset yet), OAuthService, ItemService
│   │   │   └── routers/             # health.py, auth.py (/auth/*), items.py (/items/*)
│   │   ├── alembic/                 # Migration environment (versions/ is empty)
│   │   ├── tests/                   # conftest.py + test_repositories/, test_services/, test_routers/
│   │   ├── healthcheck.py           # Container HEALTHCHECK probe (stdlib only)
│   │   ├── pyproject.toml           # PEP 621 metadata, exact pins, tool config
│   │   ├── uv.lock                  # Locked dependency resolution
│   │   ├── .python-version          # 3.13
│   │   ├── .env.example
│   │   └── Dockerfile               # targets: runtime (default, slim, non-root), dev
│   └── web/                         # Next.js app (workspace package "web")
│       ├── app/                     # App Router: /, /auth/login, /auth/register, /items
│       ├── lib/                     # api.ts (axios), auth-store.ts (zustand)
│       ├── css.d.ts                 # Type declaration for global CSS imports
│       ├── eslint.config.mjs        # Re-exports @repo/config/eslint/next
│       ├── next.config.mjs          # output: "standalone"
│       ├── tsconfig.json            # Extends @repo/config/tsconfig/nextjs.json
│       ├── .env.example
│       ├── Dockerfile               # Build context: repo root
│       └── Dockerfile.dockerignore  # Allowlist for the root build context
├── packages/
│   └── config/                      # @repo/config: tsconfig, ESLint, Prettier
├── docs/adr/                        # Architecture decision records
├── scripts/
│   ├── customize.sh                 # Placeholder replacement + local .env creation
│   ├── test-customize.sh            # Regression test for customize.sh
│   └── test-dockerignore.sh         # Regression test for the build-context ignore files
├── .github/workflows/
│   ├── ci.yml                       # api, web, scripts, docker (smoke) jobs
│   └── deploy.yml                   # Manual placeholder; nothing is deployed
├── docker-compose.yml               # postgres, api (dev target), web
├── docker-compose.smoke.yml         # Overlay: run images as packaged
├── package.json / pnpm-workspace.yaml / pnpm-lock.yaml / turbo.json / .nvmrc
├── Makefile                         # Single entry point (`make help`)
├── README.md                        # User-facing documentation
├── CLAUDE_CONTEXT.md                # This file
└── LICENSE
```

## Key Patterns and Conventions

### Placeholder Replacement System

A few files contain an app-display-name placeholder (`apps/api/app/__init__.py`, the
title of this file). Package and project names are fixed (`api`, `web`, `@repo/config`)
because they are recorded in the lockfiles. `scripts/customize.sh` replaces the
placeholders and creates the untracked `apps/api/.env` (with a generated `SECRET_KEY`)
and `apps/web/.env.local`:

```bash
./scripts/customize.sh myapp "My App" myapp.com
```

### Model Pattern

All models inherit from `Base` with mixins:

```python
from app.models.base import Base, UUIDMixin, TimestampMixin

class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    # id, created_at, updated_at added by mixins
```

### Service Pattern

Services contain business logic and use repositories (simplified example; note that
services currently raise `HTTPException`, which v2 replaces with domain exceptions):

```python
# app/services/auth.py (simplified)
class AuthService:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    def register(self, email: str, name: str, password: str) -> User:
        # Business logic: check if user exists, hash password
        existing = self.user_repo.get_by_email(email)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        # Use repository for database access
        return self.user_repo.create(
            email=email,
            name=name,
            hashed_password=hash_password(password)
        )
```

### Repository Pattern

Repositories handle database access. Note: each method currently commits on its own,
so multi-step operations are not atomic (fixed in v2 with a per-request unit of work).

```python
# app/repositories/user.py
class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, email: str, name: str, hashed_password: str) -> User:
        user = User(email=email, name=name, hashed_password=hashed_password)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user
```

### Router Pattern

Routers use services and handle HTTP concerns only (simplified example):

```python
# app/routers/auth.py (simplified)
@router.post("/register", status_code=201)
def register(
    data: RegisterRequest,
    db: Session = Depends(get_db),
) -> UserResponse:
    service = AuthService(UserRepository(db))
    user = service.register(data.email, data.name, data.password)
    return UserResponse.model_validate(user)
```

## Setup Instructions

### Prerequisites

- Docker with Compose v2 (for the full stack and Postgres)
- uv 0.13.9 (installs Python 3.13 when needed)
- Node.js 26 and pnpm 12.23.0 (`npm install -g pnpm@12.23.0`; Node 25+ has no Corepack)

### Local Development Setup

1. **Clone and customize:**
   ```bash
   git clone <repo> my-project
   cd my-project
   ./scripts/customize.sh my-project "My Project"
   ```

2. **Install dependencies:** `make setup` (`uv sync --locked` + `pnpm install --frozen-lockfile`)

3. **Backend** (needs a reachable Postgres, e.g. `docker compose up -d postgres`):
   ```bash
   cd apps/api
   cp .env.example .env   # skip if customize.sh created it
   # Tables are created by create_all() at startup; there are no migrations yet.
   uv run uvicorn app.main:app --reload
   ```

4. **Frontend:** `pnpm turbo run dev --filter web` (or `make dev`, which also starts
   postgres + api in Docker)

5. **Visit:**
   - Frontend: http://localhost:3000
   - API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

### Docker Setup

```bash
make up      # docker compose up -d (postgres, api, web)
make ps      # status, including api health
make logs    # follow logs
make down    # stop
```

## Customization Guide

### Adding a New Domain Entity

1. **Create model** (`apps/api/app/models/your_entity.py`):
   ```python
   from app.models.base import Base, UUIDMixin, TimestampMixin

   class YourEntity(Base, UUIDMixin, TimestampMixin):
       __tablename__ = "your_entities"
       name: Mapped[str] = mapped_column(String(255))
       user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
   ```

2. **Create repository** (`apps/api/app/repositories/your_entity.py`):
   ```python
   class YourEntityRepository:
       def __init__(self, db: Session):
           self.db = db

       def create(self, name: str, user_id: UUID) -> YourEntity:
           entity = YourEntity(name=name, user_id=user_id)
           self.db.add(entity)
           self.db.commit()
           self.db.refresh(entity)
           return entity
   ```

3. **Create service** (`apps/api/app/services/your_entity.py`):
   ```python
   class YourEntityService:
       def __init__(self, repo: YourEntityRepository):
           self.repo = repo

       def create(self, name: str, user_id: UUID) -> YourEntity:
           return self.repo.create(name, user_id)
   ```

4. **Create router** (`apps/api/app/routers/your_entities.py`):
   ```python
   @router.post("/your-entities")
   def create_entity(
       data: CreateYourEntityRequest,
       current_user: User = Depends(get_current_active_user),
       db: Session = Depends(get_db),
   ) -> YourEntityResponse:
       service = YourEntityService(YourEntityRepository(db))
       entity = service.create(data.name, current_user.id)
       return YourEntityResponse.model_validate(entity)
   ```

5. **Register router** in `apps/api/app/main.py`:
   ```python
   from app.routers import your_entities
   app.include_router(your_entities.router, tags=["your-entities"])
   ```

6. **Create migration:**
   ```bash
   make migration name=add_your_entities_table
   make migrate
   ```

### Changing the Example Entity (Item)

Replace all references:
- Rename `Item` model to `YourEntity`
- Update filenames: `item.py` → `your_entity.py`
- Update imports across codebase
- Run linting to catch missed references

## Testing

### Backend Tests

```bash
docker compose up -d postgres   # the app's startup hook needs Postgres
make test                       # all API tests (coverage report included)

# Specific test file
cd apps/api && uv run pytest tests/test_routers/test_items.py
```

### Test Structure

```python
# tests/conftest.py provides:
- test_db: In-memory SQLite session
- client: TestClient with test_db override
- test_user: Pre-created user fixture
- auth_headers: Authorization headers

# Example test
def test_create_item(client: TestClient, auth_headers: dict[str, str]):
    response = client.post(
        "/items",
        headers=auth_headers,
        json={"title": "Test", "description": "Test item"}
    )
    assert response.status_code == 201
```

## Deployment

### Environment Variables

Required in production:

```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/db_name

# JWT
SECRET_KEY=<generate-with-openssl rand -hex 32>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080

# OAuth (optional)
GOOGLE_CLIENT_ID=<your-client-id>
GOOGLE_CLIENT_SECRET=<your-secret>

# Frontend
NEXT_PUBLIC_API_URL=https://api.yourdomain.com
```

### Deployment

No deployment is implemented. `.github/workflows/deploy.yml` is a manual placeholder
and there is no production compose file.

### Production Checklist

- [ ] Fix the known issues listed in README.md
- [ ] Set `SECRET_KEY` to a random value (the code falls back to a public default)
- [ ] Change the hardcoded CORS origins in `apps/api/app/main.py`
- [ ] Set up HTTPS/SSL
- [ ] Configure PostgreSQL backups
- [ ] Set up monitoring & logging
- [ ] Configure CI/CD pipeline
- [ ] Run database migrations
- [ ] Set resource limits on containers

## Common Development Tasks

### Generate Database Migration

```bash
make migration name=description_of_changes
```

### Run Linting and Type Checking

```bash
make lint        # ruff check + ESLint
make typecheck   # mypy + tsc
```

### Format Code

```bash
make fmt         # ruff format + Prettier
make fmt-check   # what CI enforces
```

### Add Python Dependency

Pin exact versions (check the current release first):

```bash
cd apps/api
uv add 'package_name==X.Y.Z'           # runtime dependency
uv add --dev 'package_name==X.Y.Z'     # dev dependency group
```

### Add JavaScript Dependency

Pin exact versions (check the current release first):

```bash
pnpm --filter web add --save-exact package_name
pnpm --filter web add --save-exact --save-dev dev-package-name
```

## API Endpoints

### Health
- `GET /health` - Health check

### Authentication
- `POST /auth/register` - Register new user
- `POST /auth/login` - Login (returns JWT token)
- `GET /auth/me` - Get current user (requires auth)
- `PATCH /auth/me` - Update profile (requires auth)
- `GET /auth/google/login` - Returns the Google authorization URL
- `GET /auth/google/callback` - OAuth callback; redirects to `FRONTEND_URL/auth/callback?token=...` (that page does not exist in the client yet)

### Items (Example CRUD)
- `GET /items` - List items (requires auth)
- `POST /items` - Create item (requires auth)
- `GET /items/{id}` - Get item (requires auth)
- `PATCH /items/{id}` - Update item (requires auth)
- `DELETE /items/{id}` - Delete item (requires auth)

## Frontend Architecture

### Pages
- `/` - Home page
- `/auth/login` - Login form
- `/auth/register` - Registration form
- `/items` - Items CRUD page (protected)

### State Management
- **Zustand** (`lib/auth-store.ts`): Authentication state (user, token, login/logout)
- **Component State**: Local state with `useState` for forms

### API Client
- **Axios** (`lib/api.ts`): HTTP client with automatic token injection and 401 handling
- Base URL from `NEXT_PUBLIC_API_URL` environment variable

### Styling
- **Vanilla CSS** (`app/globals.css`): No build-time dependency
- Simple class-based approach (`.button`, `.card`, `.error`, etc.)
- Responsive grid layout patterns

## Git Workflow

```bash
# Feature branch
git checkout -b feature/your-feature

# Make changes, commit frequently
git add .
git commit -m "Clear commit message"

# Push and create PR
git push origin feature/your-feature

# GitHub Actions will run tests automatically
```

## Troubleshooting

### Database Connection Error
- Ensure PostgreSQL is running: `docker compose up -d postgres`
- Check DATABASE_URL in .env
- Verify migrations: `alembic current`

### 401 Unauthorized on API calls
- Token expired? Re-login in frontend
- Check Authorization header is sent
- Verify SECRET_KEY matches between backend and token generation

### CORS Errors
- CORS origins are hardcoded in `apps/api/app/main.py`
- Frontend URL must be in allowed origins
- In development, should be `["http://localhost:3000"]`

### Migration Conflicts
- Check alembic/versions/ for conflicts
- Merge conflicts manually if needed
- Run `alembic upgrade head` to apply all migrations

### Frontend not connecting to API
- Check NEXT_PUBLIC_API_URL in .env.local
- Ensure API is running on expected port
- Check browser console for CORS errors

## Code Review Standards

- All changes go through pull requests
- GitHub Actions tests must pass before merge
- Code should follow project patterns (3-layer backend, component-based frontend)
- Meaningful commit messages required
- Documentation updated for public APIs

## Performance Considerations

- JWT tokens are stored in browser localStorage
- Frontend uses Next.js built-in code splitting
- SQLAlchemy's default connection pool is used (`pool_pre_ping=True`)

## Security Notes

- Passwords hashed with bcrypt
- Stateless 7-day JWT access tokens (no refresh tokens, revocation or rate limiting yet)
- CORS origins hardcoded to localhost in `apps/api/app/main.py`
- SQL injection prevented by SQLAlchemy ORM
- XSS mitigated by React's JSX escaping (but tokens in localStorage are readable by any XSS)
- No cookies are used, so there is no CSRF protection to speak of; see README.md known issues

## License

MIT License - See LICENSE file

## Contributing

This boilerplate can be customized and extended freely. Common modifications:

1. Replace `Item` entity with your domain model
2. Add additional auth providers (GitHub, Microsoft, etc.)
3. Implement role-based access control (RBAC)
4. Add file upload/storage
5. Add real-time features with WebSockets
6. Customize styling and UI components

## Support

For issues or questions:
1. Check the troubleshooting section
2. Review similar patterns in existing code
3. Check test files for usage examples
4. Refer to framework documentation (FastAPI, Next.js, SQLAlchemy)

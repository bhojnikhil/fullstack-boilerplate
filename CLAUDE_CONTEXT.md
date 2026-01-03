# {{APP_NAME}} - Full-Stack Boilerplate Context

This document provides comprehensive context for AI-assisted development on this full-stack boilerplate.

## Architecture Overview

This is a 3-tier full-stack application:

```
Frontend (Next.js 15)
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
├── api/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app initialization
│   │   ├── auth/                # Authentication utilities
│   │   │   ├── security.py      # Password hashing, JWT tokens
│   │   │   └── dependencies.py  # FastAPI dependencies (get_current_user, get_db)
│   │   ├── core/
│   │   │   ├── config.py        # Pydantic settings (with {{PLACEHOLDER}} system)
│   │   │   └── db.py            # SQLAlchemy session, Base declarative
│   │   ├── models/              # SQLAlchemy ORM models
│   │   │   ├── base.py          # UUIDMixin, TimestampMixin
│   │   │   ├── user.py          # User model + OAuthAccount
│   │   │   └── item.py          # Item example (customize for your domain entity)
│   │   ├── schemas/             # Pydantic request/response models
│   │   │   ├── user.py
│   │   │   └── item.py
│   │   ├── repositories/        # Database access layer
│   │   │   ├── user.py          # UserRepository
│   │   │   └── item.py          # ItemRepository
│   │   ├── services/            # Business logic layer
│   │   │   ├── auth.py          # AuthService (register, login, password reset)
│   │   │   ├── oauth.py         # OAuthService (Google OAuth 2.0)
│   │   │   └── item.py          # ItemService (CRUD example)
│   │   └── routers/             # HTTP endpoints
│   │       ├── health.py        # Health check
│   │       ├── auth.py          # /auth/* routes
│   │       └── items.py         # /items/* routes
│   ├── alembic/                 # Database migrations
│   │   ├── env.py               # Migration environment
│   │   ├── script.py.mako       # Migration template
│   │   └── versions/            # Generated migrations (auto-generated)
│   ├── tests/
│   │   ├── conftest.py          # Pytest fixtures (test_db, client, auth_headers)
│   │   ├── test_repositories/
│   │   ├── test_services/
│   │   └── test_routers/
│   ├── .env.example             # Environment template
│   ├── pyproject.toml           # Python dependencies + Poetry config
│   └── Dockerfile
├── client/
│   ├── app/                     # Next.js app directory
│   │   ├── layout.tsx           # Root layout
│   │   ├── page.tsx             # Home page
│   │   ├── globals.css          # Global styles
│   │   ├── auth/
│   │   │   ├── login/page.tsx
│   │   │   └── register/page.tsx
│   │   └── items/page.tsx       # Items CRUD page
│   ├── lib/
│   │   ├── api.ts               # Axios API client with interceptors
│   │   └── auth-store.ts        # Zustand auth store
│   ├── package.json
│   ├── tsconfig.json
│   ├── next.config.js
│   ├── .env.example
│   └── Dockerfile
├── infra/                       # Infrastructure as Code (optional)
├── scripts/
│   └── customize.sh             # Automated placeholder replacement
├── .github/workflows/
│   ├── test.yml                 # Pytest + linting + type checking
│   └── deploy.yml               # Deployment template
├── docker-compose.yml           # Local development stack
├── Makefile                     # Development commands
├── Makefile.docker              # Docker-compose commands
├── README.md                    # User-facing documentation
├── CLAUDE_CONTEXT.md            # This file
└── LICENSE
```

## Key Patterns and Conventions

### Placeholder Replacement System

All configuration uses `{{PLACEHOLDER}}` format for automated replacement:

```python
# api/app/core/config.py
APP_NAME: str = "{{APP_NAME}}"
PROJECT_NAME: str = "{{PROJECT_NAME}}"

# Replaced by scripts/customize.sh when setting up new project
```

After cloning, run:
```bash
./scripts/customize.sh
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

Services contain ONLY business logic and use repositories:

```python
# app/services/auth.py
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

Repositories handle ONLY database access:

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

Routers use services and handle HTTP concerns only:

```python
# app/routers/auth.py
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

- Python 3.13+
- Node.js 20+
- PostgreSQL 16+ (or use Docker)
- Docker & Docker Compose (optional, for containerized setup)

### Local Development Setup

1. **Clone and customize:**
   ```bash
   git clone <repo> my-project
   cd my-project
   ./scripts/customize.sh
   ```

2. **Backend setup:**
   ```bash
   cd api
   poetry install
   cp .env.example .env
   # Edit .env with your settings
   poetry run alembic upgrade head
   poetry run uvicorn app.main:app --reload
   ```

3. **Frontend setup:**
   ```bash
   cd client
   npm install
   cp .env.example .env.local
   npm run dev
   ```

4. **Visit:**
   - Frontend: http://localhost:3000
   - API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

### Docker Setup

```bash
# Build images
docker-compose build

# Start services (postgres, api, client)
docker-compose up -d

# Watch logs
docker-compose logs -f

# Stop
docker-compose down
```

## Customization Guide

### Adding a New Domain Entity

1. **Create model** (`api/app/models/your_entity.py`):
   ```python
   from app.models.base import Base, UUIDMixin, TimestampMixin

   class YourEntity(Base, UUIDMixin, TimestampMixin):
       __tablename__ = "your_entities"
       name: Mapped[str] = mapped_column(String(255))
       user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
   ```

2. **Create repository** (`api/app/repositories/your_entity.py`):
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

3. **Create service** (`api/app/services/your_entity.py`):
   ```python
   class YourEntityService:
       def __init__(self, repo: YourEntityRepository):
           self.repo = repo

       def create(self, name: str, user_id: UUID) -> YourEntity:
           return self.repo.create(name, user_id)
   ```

4. **Create router** (`api/app/routers/your_entities.py`):
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

5. **Register router** in `api/app/main.py`:
   ```python
   from app.routers import your_entities
   app.include_router(your_entities.router, tags=["your-entities"])
   ```

6. **Create migration:**
   ```bash
   poetry run alembic revision --autogenerate -m "Add your_entities table"
   poetry run alembic upgrade head
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
cd api

# Run all tests
poetry run pytest tests/ -v

# Run specific test file
poetry run pytest tests/test_routers/test_items.py -v

# With coverage
poetry run pytest tests/ --cov=app --cov-report=html
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

### Docker Deployment

1. **Push images to registry:**
   ```bash
   docker tag my-api:latest registry.example.com/my-api:latest
   docker push registry.example.com/my-api:latest
   ```

2. **Deploy with docker-compose:**
   ```bash
   docker-compose -f docker-compose.prod.yml up -d
   ```

### Production Checklist

- [ ] Change `SECRET_KEY` to a random value
- [ ] Set `ENVIRONMENT=production` in config
- [ ] Configure CORS_ORIGINS in settings
- [ ] Set up HTTPS/SSL
- [ ] Configure PostgreSQL backups
- [ ] Set up monitoring & logging
- [ ] Configure CI/CD pipeline
- [ ] Run database migrations
- [ ] Set resource limits on containers

## Common Development Tasks

### Generate Database Migration

```bash
cd api
poetry run alembic revision --autogenerate -m "Description of changes"
```

### Run Linting and Type Checking

```bash
cd api
poetry run ruff check .
poetry run mypy app

cd ../client
npm run lint
npm run type-check
```

### Format Code

```bash
cd api
poetry run ruff format .

cd ../client
npm run format
```

### Add Python Dependency

```bash
cd api
poetry add package_name
poetry lock
```

### Add JavaScript Dependency

```bash
cd client
npm install package_name
npm install --save-dev dev-package-name
```

## API Endpoints

### Health
- `GET /health` - Health check

### Authentication
- `POST /auth/register` - Register new user
- `POST /auth/login` - Login (returns JWT token)
- `GET /auth/me` - Get current user (requires auth)
- `POST /auth/refresh` - Refresh token (optional)

### Items (Example CRUD)
- `GET /items` - List items (requires auth)
- `POST /items` - Create item (requires auth)
- `GET /items/{id}` - Get item (requires auth)
- `PUT /items/{id}` - Update item (requires auth)
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
- Ensure PostgreSQL is running: `docker-compose up postgres`
- Check DATABASE_URL in .env
- Verify migrations: `alembic current`

### 401 Unauthorized on API calls
- Token expired? Re-login in frontend
- Check Authorization header is sent
- Verify SECRET_KEY matches between backend and token generation

### CORS Errors
- Check CORS_ORIGINS in `api/app/core/config.py`
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

- Database queries use indexes on frequently filtered columns
- JWT tokens cached in browser localStorage
- Frontend uses Next.js built-in code splitting
- API caching headers configured for static responses
- Database connection pooling enabled

## Security Notes

- All passwords hashed with bcrypt
- JWT tokens for stateless authentication
- CORS configured to prevent unauthorized access
- SQL injection prevented by SQLAlchemy ORM
- XSS prevented by React's JSX escaping
- CSRF protection via SameSite cookie policy

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

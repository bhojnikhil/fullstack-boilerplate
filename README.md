# Full-Stack Boilerplate

Production-ready monorepo template with **FastAPI** + **Next.js** 16, built for rapid development.

## Features

✅ **Backend**
- FastAPI with 3-layer architecture (Router → Service → Repository)
- PostgreSQL with SQLAlchemy ORM and Alembic migrations
- JWT authentication + Google OAuth integration
- Type-safe with Python 3.13+ and mypy strict mode

✅ **Frontend**
- Next.js 16 with App Router and React 19
- TypeScript with strict mode
- shadcn/ui component library (20+ components)
- Dark/light mode theme system
- Responsive design (mobile-first)

✅ **DevOps**
- Docker with multi-stage production builds
- Development mode with hot reload
- Caddy reverse proxy with automatic HTTPS
- Full CI/CD with GitHub Actions
- Pre-commit hooks (ruff, mypy, ESLint, Prettier)

✅ **Testing**
- Backend: pytest with 80% coverage requirement
- Frontend: Vitest with React Testing Library
- Example tests included

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Make
- Git

### 5-Minute Setup

```bash
# Clone and customize
git clone https://github.com/you/fullstack-boilerplate myapp
cd myapp
./scripts/customize.sh myapp "My App" mydomain.com

# Configure environment
cp api/.env.example api/.env
cp client/.env.local.example client/.env.local
# Edit .env files with your values (especially GOOGLE_CLIENT_ID, etc.)

# Start development environment
make up

# Create first user
# Visit http://localhost:3000/login
# Click "Sign Up" tab
# Enter email, password, name

# Done! Your app is running at http://localhost:3000
```

## Tech Stack

**Backend:**
- Python 3.13+
- FastAPI 0.115+
- PostgreSQL 16
- SQLAlchemy 2.0
- Alembic
- Poetry (dependency management)

**Frontend:**
- Next.js 16
- React 19.2
- TypeScript 5
- Tailwind CSS 4
- shadcn/ui
- Vitest

**DevOps:**
- Docker & Docker Compose
- Caddy (reverse proxy)
- GitHub Actions (CI/CD)
- Pre-commit hooks

## Architecture

### Backend Structure
```
api/
├── app/
│   ├── core/          # Database, config, dependencies
│   ├── models/        # SQLAlchemy models
│   ├── schemas/       # Pydantic request/response
│   ├── repositories/  # Data access layer
│   ├── services/      # Business logic
│   ├── routers/       # API endpoints
│   └── auth/          # Authentication
├── alembic/           # Database migrations
└── tests/             # Test suite
```

### Frontend Structure
```
client/
├── app/               # Next.js App Router pages
├── components/        # React components
├── lib/               # Utilities, API client
├── hooks/             # Custom React hooks
└── __tests__/         # Test suite
```

## Key Concepts

### Backend: 3-Layer Architecture

**Router** → Handles HTTP requests
**Service** → Contains business logic
**Repository** → Manages database access

This separation ensures:
- Testability (mock repositories for unit tests)
- Maintainability (clear responsibilities)
- Reusability (services can be called from multiple routers)

### Frontend: API-Driven

All API calls go through `lib/api.ts` which:
- Automatically injects JWT tokens
- Provides type-safe API methods
- Handles error responses
- Supports offline fallbacks

### Authentication

1. **Email/Password:**
   - User registers with email, password, name
   - Password hashed with bcrypt
   - JWT token returned and stored

2. **Google OAuth:**
   - User clicks "Sign in with Google"
   - Redirects to Google login
   - OAuth callback creates/links user
   - JWT token returned

## Development

### Common Commands

```bash
# Start dev environment
make up

# View logs
make logs

# Run migrations
make migrate

# Create new migration
make migration NAME='add_column'

# Run tests
make test

# Run tests with coverage
make test-coverage

# Format code
make format

# Lint code
make lint

# Reset database
make fresh
```

### Project Structure

The boilerplate includes a simple **Item** entity as a CRUD example. You can:
- View the pattern in `api/app/models/item.py`
- Follow the same pattern for your domain entities
- Replace "Item" with your entity name throughout the project

## Documentation

- **[SETUP.md](./SETUP.md)** - Detailed setup and configuration
- **[CUSTOMIZATION.md](./CUSTOMIZATION.md)** - How to customize the boilerplate
- **[ARCHITECTURE.md](./ARCHITECTURE.md)** - Technical architecture details
- **[DEPLOYMENT.md](./DEPLOYMENT.md)** - Deployment instructions

## API Documentation

Once running, visit:
- API Docs: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Testing

### Backend Tests
```bash
# Run all tests
make test

# Run specific test file
docker-compose exec api-dev pytest tests/test_routers/test_items.py -v

# Run with coverage
make test-coverage
```

### Frontend Tests
```bash
cd client
npm test -- --watch
```

## Deployment

The boilerplate is ready for production deployment. See [DEPLOYMENT.md](./DEPLOYMENT.md) for:
- Docker Compose on VPS (DigitalOcean, Linode, etc.)
- Vercel (frontend) + Railway (backend)
- Environment configuration
- SSL/HTTPS setup

## Example Customization

To adapt this boilerplate for a "Todo App":

1. **Rename Item entity:**
   - `api/app/models/item.py` → `todo.py`
   - Replace class `Item` with `Todo`
   - Update FK/relationships

2. **Update endpoints:**
   - `api/app/routers/items.py` → `todos.py`
   - Update route paths to `/todos`

3. **Update frontend:**
   - Rename pages: `items/` → `todos/`
   - Update API client calls
   - Update component names

See [CUSTOMIZATION.md](./CUSTOMIZATION.md) for detailed guide.

## Contributing

1. Create feature branch: `git checkout -b feature/my-feature`
2. Write tests for new features
3. Run pre-commit hooks: `pre-commit run --all-files`
4. Ensure CI passes
5. Submit pull request

Pre-commit hooks automatically:
- Format code (ruff, prettier)
- Check types (mypy)
- Lint code (ruff, eslint)
- Validate YAML/JSON

## License

MIT - See [LICENSE](./LICENSE)

## Support

For issues and questions:
- Read [SETUP.md](./SETUP.md) for setup help
- Check [ARCHITECTURE.md](./ARCHITECTURE.md) for design patterns
- Review existing examples in the codebase

## Next Steps

1. ✅ Clone this repository
2. ✅ Run `./scripts/customize.sh` to personalize
3. ✅ Configure environment variables
4. ✅ Run `make up` to start
5. ✅ Visit http://localhost:3000
6. ✅ Start building your features!

Happy building! 🚀

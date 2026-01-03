import Link from "next/link";

export default function Home() {
  return (
    <>
      <header className="header">
        <div className="container">
          <h1>Boilerplate App</h1>
        </div>
      </header>

      <main className="main">
        <div className="container">
          <div className="card">
            <h2>Welcome to Boilerplate App</h2>
            <p>
              This is a full-stack boilerplate with Next.js frontend and FastAPI
              backend.
            </p>

            <div style={{ marginTop: "2rem", display: "flex", gap: "1rem" }}>
              <Link href="/auth/login" className="button">
                Login
              </Link>
              <Link href="/auth/register" className="button button-secondary">
                Register
              </Link>
              <Link href="/items" className="button button-secondary">
                Items
              </Link>
            </div>

            <div style={{ marginTop: "2rem" }}>
              <h3>Getting Started</h3>
              <ol>
                <li>Run migrations: <code>alembic upgrade head</code></li>
                <li>Start backend: <code>cd api && poetry run uvicorn app.main:app --reload</code></li>
                <li>Start frontend: <code>cd client && npm run dev</code></li>
                <li>Visit <code>http://localhost:3000</code></li>
              </ol>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}

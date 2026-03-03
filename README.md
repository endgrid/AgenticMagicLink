# Agentic Magic Link Monorepo

This repository now uses a monorepo layout with a React chat frontend and a FastAPI backend that manages an in-memory agent workflow session.

## Repository layout

- `frontend/`: React + Vite chat UI that creates a session and sends chat turns.
- `backend/`: FastAPI API for session creation and workflow turn processing.
- `infra/`: Placeholder folder for IaC templates and deployment artifacts.

## Architecture overview

1. The frontend boots and calls `POST /api/chat/session`.
2. The backend returns a `session_id` and initializes shared session state.
3. User messages are posted to `POST /api/chat/message`.
4. The backend updates in-memory state fields:
   - `required_functions`
   - `target_account_id`
   - `generated_policy_json`
   - `magic_link_script`
5. The backend responds with full message history including assistant summary.

## Local setup

1. Copy environment values:

   ```bash
   cp .env.example .env
   ```

2. Start backend:

   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   uvicorn app.main:app --reload --host 0.0.0.0 --port ${BACKEND_PORT:-8000}
   ```

3. Start frontend in a new shell:

   ```bash
   cd frontend
   npm install
   npm run dev -- --host 0.0.0.0 --port ${FRONTEND_PORT:-5173}
   ```

4. Open the frontend URL and chat with the workflow assistant.

## Linting and formatting

### Frontend

```bash
cd frontend
npm run lint
npm run format
```

### Backend

```bash
cd backend
ruff check .
ruff format .
black .
```

## API endpoints

- `POST /api/chat/session`: Creates a new session and returns `session_id`.
- `POST /api/chat/message`: Accepts `session_id`, `message`, and optional `history`, then returns updated transcript.
- `GET /health`: Basic service health check.

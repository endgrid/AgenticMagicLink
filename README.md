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
   - `generated_policy_json` (generated via Amazon Bedrock when policy generation is requested)
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


## Bedrock policy generation configuration

The backend `InMemorySessionStore` now calls `BedrockClient.generate_policy_from_functions` when a user message asks for policy generation.

Set **one** of these model ID configuration options:

- `BEDROCK_MODEL_ID` (direct value).
- `BEDROCK_MODEL_ID_PARAMETER` (SSM Parameter Store name containing the model ID).
- `BEDROCK_MODEL_ID_SECRET_ID` (+ optional `BEDROCK_MODEL_ID_SECRET_KEY`, default `model_id`) for Secrets Manager.

Optional operational settings:

- `POLICY_GENERATION_DLQ_URL` to send failed synchronous policy-generation events to SQS for offline triage/replay.
- `BEDROCK_MAX_ATTEMPTS` to control synchronous Bedrock retries in-path (defaults to 2).

See `infra/lambda_iam_policy_example.json` for least-privilege IAM granting `bedrock:InvokeModel` only on approved model ARNs.

# Agentic Magic Link

Agentic Magic Link is a monorepo for generating short-lived AWS "magic link" access scripts through a guided chat workflow.

It includes:
- a **React + Vite frontend** chat interface (`frontend/`), and
- a **FastAPI backend** (`backend/`) that tracks workflow state in memory, optionally generates IAM policy JSON with Amazon Bedrock, and returns an executable Python script payload.

## Repository layout

- `frontend/` – Web chat UI.
- `backend/` – FastAPI app, domain models, session store, Lambda handlers, and tests.
- `infra/` – Deployment assets (CloudFormation + Terraform snippets, deploy script).
- `app.py` / `test_app.py` – Legacy standalone workflow example used by root-level tests.

## How the application works

### 1) Session creation

The frontend starts by calling:

- `POST /api/chat/session`

The backend creates an in-memory session and returns:
- `session_id`
- `initial_assistant_message`
- `next_expected_input` (initially `work_description`)

### 2) Guided workflow via chat messages

For each user message, the frontend calls:

- `POST /api/chat/message`

The backend updates session state in this order:
1. **Work description / required functions**
2. **Target AWS account ID** (12 digits)
3. **Target IAM role ARN** (`arn:aws:iam::<account>:role/...`)
4. **Session duration (seconds)** between **900** and **43200**

The response always includes updated transcript messages plus `next_expected_input` so the UI can guide what the user should enter next.

### 3) Policy generation (optional)

If a message asks to generate a policy (contains `policy`), the backend tries to call Amazon Bedrock and stores the generated policy JSON in session state.

Failure paths are logged, and failed policy-generation events can be pushed to SQS if a DLQ URL is configured.

### 4) Magic link script generation

Once account ID, role ARN, and valid duration are present, the backend generates a Python script payload and returns:
- script `content`
- `checksum_sha256`
- script `version`

The assistant message also includes run instructions.

## API contract

### `POST /api/chat/session`
Creates a new in-memory workflow session.

### `POST /api/chat/message`
Request body fields:
- `session_id` (required)
- `message` (required)
- `history` (optional prior transcript)

Response fields include:
- `messages`
- `next_expected_input`
- optional `magic_link_script` with `content`, `checksum_sha256`, and `version`

### `GET /health`
Simple health endpoint returning `{ "status": "ok" }`.

## Frontend/backend contract

- The frontend only calls backend HTTP APIs.
- The frontend requires `VITE_API_BASE_URL` and trims trailing `/` automatically.
- AWS SDK calls happen on the backend only.

## Configuration

### Frontend

Required environment variable:
- `VITE_API_BASE_URL` (for example: `http://localhost:8000`)

### Backend

#### Bedrock model ID source (set one)
- `BEDROCK_MODEL_ID`
- `BEDROCK_MODEL_ID_PARAMETER` (SSM Parameter Store name)
- `BEDROCK_MODEL_ID_SECRET_ID` (Secrets Manager secret id)
  - optional `BEDROCK_MODEL_ID_SECRET_KEY` (default: `model_id`)

#### Optional runtime settings
- `BEDROCK_MAX_ATTEMPTS` (default `2`)
- `POLICY_FAILURE_DLQ_URL` (SQS URL for failed policy generation events)

## Local development

### Backend

From repo root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

Alternative (from `backend/`):

```bash
make run
```

### Frontend

```bash
cd frontend
npm install
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

## Running tests

### Backend tests

```bash
cd backend
pytest -q
```

### Legacy root workflow tests

```bash
pytest -q test_app.py
```

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
make lint
make format
```

## Infrastructure assets

Infra templates and scripts live under `infra/` for static frontend hosting and AWS infrastructure scaffolding.

## Notes and limitations

- Session state is **in-memory**; restarting the backend clears active sessions.
- CORS is currently permissive (`*`) in backend app setup.
- Bedrock integration is optional and only used when policy generation is requested.

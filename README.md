# Agentic Magic Link Monorepo

This repository uses a monorepo layout with a React chat frontend and a FastAPI backend that manages an in-memory agent workflow session.

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

### Frontend/backend dependency contract

- The browser frontend talks **only** to the backend API endpoint configured by `VITE_API_BASE_URL`.
- The frontend does **not** use AWS SDK clients directly and does **not** perform Cognito/AWS auth flows in the browser.
- All AWS service access (Bedrock, optional SSM/Secrets Manager reads, optional SQS DLQ writes) happens server-side in the backend.

### AWS services used (auditable scope)

This application does **not** use "all AWS services." It currently uses only the services listed below.

| Service | Required/Optional | Runtime purpose | Where configured |
| --- | --- | --- | --- |
| Amazon Bedrock Runtime | Optional | Generate IAM policy JSON from function metadata when policy generation is requested. | Backend env (`BEDROCK_MODEL_ID`, `BEDROCK_MODEL_ID_PARAMETER`, or `BEDROCK_MODEL_ID_SECRET_ID`) and backend code (`backend/src/bedrock_client.py`). |
| AWS Systems Manager Parameter Store | Optional | Resolve Bedrock model ID at runtime when `BEDROCK_MODEL_ID_PARAMETER` is set. | Backend env (`BEDROCK_MODEL_ID_PARAMETER`) and backend code (`backend/src/bedrock_client.py`). |
| AWS Secrets Manager | Optional | Resolve Bedrock model ID at runtime when `BEDROCK_MODEL_ID_SECRET_ID` is set. | Backend env (`BEDROCK_MODEL_ID_SECRET_ID`, optional `BEDROCK_MODEL_ID_SECRET_KEY`) and backend code (`backend/src/bedrock_client.py`). |
| Amazon SQS | Optional | Receive failed synchronous policy-generation events when a DLQ URL is configured. | Backend env (`POLICY_GENERATION_DLQ_URL`) and backend code (`backend/app/services/session_store.py`). |
| Amazon DynamoDB | Optional (future) | Not used at runtime in the current implementation; session state is in-memory only. Reserved for a future persistent session store. | Placeholder template only: `infra/dynamodb-sessions.yaml`. |

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

## Running exported magic-link scripts locally

When the backend captures a `magic_link_script`, the API response includes the full script content and metadata (`checksum_sha256`, `version`) so you can save and verify it before running.

### Local prerequisites

- `python` 3.11+ available on your workstation (`python --version`).
- `boto3` installed in the environment used to execute the script (`pip install boto3`).
- AWS credentials available from a standard provider chain source (for example environment variables, shared credentials file, AWS SSO, or an instance/task role).

### Safe default execution example

```bash
# Save response payload field magic_link_script.content into a local file
cat > magic_link.py <<'PY'
<PASTE_SCRIPT_CONTENT_HERE>
PY

# Optional: verify checksum from magic_link_script.checksum_sha256
python - <<'PY'
import hashlib
from pathlib import Path
print(hashlib.sha256(Path('magic_link.py').read_bytes()).hexdigest())
PY

# Run with least-privilege defaults and short-lived session
python magic_link.py \
  --role-arn arn:aws:iam::123456789012:role/ExampleFederationRole \
  --session-name local-magic-link \
  --region us-east-1
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
ruff check .
ruff format .
black .
```

## API endpoints

- `POST /api/chat/session`: Creates a new session and returns `session_id`.
- `POST /api/chat/message`: Accepts `session_id`, `message`, and optional `history`, then returns updated transcript plus optional `magic_link_script` payload (script content + checksum/version metadata).
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

# Infrastructure

Terraform configuration for deploying the backend chat API on AWS Lambda + API Gateway HTTP API.

- Frontend static hosting.
- Backend API service.
- Session store replacement (Redis/DynamoDB) when moving beyond in-memory state.

## DynamoDB session table

`dynamodb-sessions.yaml` provisions a DynamoDB table keyed by `session_id`.

- **TTL attribute:** `expires_at`
- **Optimistic locking attribute:** `version` (enforced by conditional `UpdateItem` in the backend)

### Deploy

```bash
aws cloudformation deploy \
  --template-file infra/dynamodb-sessions.yaml \
  --stack-name agentic-magic-link-sessions \
  --capabilities CAPABILITY_NAMED_IAM
```

### Backend configuration

Set these environment variables for the API service:

- `SESSION_TABLE_NAME` (default: `agentic-magic-link-sessions`)
- `SESSION_TTL_SECONDS` (default: `3600`)

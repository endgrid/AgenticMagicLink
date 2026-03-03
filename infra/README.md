# Infrastructure

Terraform configuration for deploying the backend chat API on AWS Lambda + API Gateway HTTP API.

## What this defines

- Two Lambda functions for existing chat routes:
  - `POST /api/chat/session`
  - `POST /api/chat/message`
- IAM execution role with CloudWatch Logs permissions.
- API Gateway HTTP API routes/integrations/stage.
- Lambda environment variable wiring, including `BEDROCK_MODEL_ID`.
- Permissive CORS equivalent to FastAPI middleware in `backend/app/main.py`:
  - `allow_origins = ["*"]`
  - `allow_methods = ["*"]`
  - `allow_headers = ["*"]`
  - `allow_credentials = true`

## Files

- `terraform/main.tf`
- `terraform/variables.tf`
- `terraform/outputs.tf`

## Deploy quick start

1. Build and zip backend code so the package contains the `backend/` package.
2. Initialize Terraform:

```bash
cd infra/terraform
terraform init
```

3. Plan/apply:

```bash
terraform plan -var="lambda_package_path=../../backend.zip" -var="bedrock_model_id=<model-id>"
terraform apply -var="lambda_package_path=../../backend.zip" -var="bedrock_model_id=<model-id>"
```

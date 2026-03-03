# Infrastructure

This folder defines the currently scoped infrastructure for static frontend hosting and deployment.

## AWS services used (auditable scope)

This infra package does **not** provision "all AWS services." It only provisions or references the services listed below.

| Service | Required/Optional | Runtime purpose | Where configured |
| --- | --- | --- | --- |
| Amazon S3 | Required | Store built frontend assets as a private static origin. | `infra/cloudformation/frontend-static-site.yaml`, `infra/scripts/deploy_frontend.sh`. |
| Amazon CloudFront | Required | Serve frontend assets globally and provide SPA routing fallback behavior. | `infra/cloudformation/frontend-static-site.yaml`, `infra/scripts/deploy_frontend.sh`. |
| AWS CloudFormation | Required (for this deployment path) | Provision S3 + CloudFront hosting resources from template. | `infra/cloudformation/frontend-static-site.yaml` and deployment commands in this README. |
| Amazon API Gateway | Optional/external dependency | Acts as the backend API URL injected into the frontend build (`API_BASE_URL`), but is not provisioned in this folder. | Referenced by `API_BASE_URL` in `infra/scripts/deploy_frontend.sh`. |
| Amazon Cognito | Optional (future) | Not used in current baseline; listed as a future extension for authenticated APIs. | Described only in the "Identity and authorization" section of this README. |
| Amazon DynamoDB | Optional (future) | Not used by this frontend hosting stack; placeholder session table template exists for future backend persistence. | `infra/dynamodb-sessions.yaml`. |

## Frontend static hosting resources

Template: `cloudformation/frontend-static-site.yaml`

It provisions:

- S3 bucket for static assets (private, versioned).
- CloudFront Origin Access Control (OAC).
- CloudFront distribution configured for SPA fallback to `index.html`.
- Bucket policy granting read access only to the distribution.

### Deploy infrastructure

```bash
aws cloudformation deploy \
  --stack-name agentic-magic-link-frontend \
  --template-file infra/cloudformation/frontend-static-site.yaml \
  --parameter-overrides FrontendBucketName=<globally-unique-bucket-name> \
  --capabilities CAPABILITY_NAMED_IAM
```

Capture outputs:

```bash
aws cloudformation describe-stacks \
  --stack-name agentic-magic-link-frontend \
  --query 'Stacks[0].Outputs[].[OutputKey,OutputValue]' \
  --output table
```

## Build + publish frontend

Script: `scripts/deploy_frontend.sh`

Required environment variables:

- `S3_BUCKET_NAME`: From `FrontendBucketName` output.
- `CLOUDFRONT_DISTRIBUTION_ID`: From `FrontendDistributionId` output.
- `API_BASE_URL`: API Gateway invoke URL to inject at build time.

Example:

```bash
export S3_BUCKET_NAME=<bucket>
export CLOUDFRONT_DISTRIBUTION_ID=<distribution-id>
export API_BASE_URL=https://<api-id>.execute-api.<region>.amazonaws.com/<stage>

bash infra/scripts/deploy_frontend.sh
```

## API endpoint injection

The frontend reads `VITE_API_BASE_URL` at build time in `frontend/src/api.ts`.

If unset, it defaults to `http://localhost:8000` for local development.

### Frontend dependency contract

- Browser code calls only the backend API URL (`VITE_API_BASE_URL`).
- Browser code does not call AWS services directly and does not include AWS SDK/Cognito auth integration in this baseline.
- AWS integrations are expected to remain server-side (backend/API layer).

## Identity and authorization

Current API routes are anonymous and do not require user identity.

Cognito User Pool/Hosted UI is intentionally not added in this baseline deployment. If API authorization requirements change, add:

1. Cognito User Pool + App Client + Hosted UI.
2. API Gateway JWT authorizer bound to Cognito issuer/audience.
3. Frontend auth flow to acquire and pass bearer token in API requests.

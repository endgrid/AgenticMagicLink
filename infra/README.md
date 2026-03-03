# Infrastructure

This folder includes a CloudFormation template and deployment script for shipping the React frontend to a private S3 origin fronted by CloudFront.

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

## Identity and authorization

Current API routes are anonymous and do not require user identity.

Cognito User Pool/Hosted UI is intentionally not added in this baseline deployment. If API authorization requirements change, add:

1. Cognito User Pool + App Client + Hosted UI.
2. API Gateway JWT authorizer bound to Cognito issuer/audience.
3. Frontend auth flow to acquire and pass bearer token in API requests.

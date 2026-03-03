#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"

: "${S3_BUCKET_NAME:?S3_BUCKET_NAME is required}"
: "${CLOUDFRONT_DISTRIBUTION_ID:?CLOUDFRONT_DISTRIBUTION_ID is required}"
: "${API_BASE_URL:?API_BASE_URL is required (e.g. https://abc123.execute-api.us-east-1.amazonaws.com/prod)}"

if ! command -v aws >/dev/null 2>&1; then
  echo "aws CLI is required." >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required." >&2
  exit 1
fi

echo "Installing frontend dependencies..."
if [[ -f "$FRONTEND_DIR/package-lock.json" ]]; then
  npm --prefix "$FRONTEND_DIR" ci
else
  npm --prefix "$FRONTEND_DIR" install
fi

echo "Building frontend with API endpoint: $API_BASE_URL"
VITE_API_BASE_URL="$API_BASE_URL" npm --prefix "$FRONTEND_DIR" run build

echo "Syncing assets to s3://$S3_BUCKET_NAME"
aws s3 sync "$FRONTEND_DIR/dist" "s3://$S3_BUCKET_NAME" --delete

echo "Creating CloudFront invalidation for distribution $CLOUDFRONT_DISTRIBUTION_ID"
aws cloudfront create-invalidation \
  --distribution-id "$CLOUDFRONT_DISTRIBUTION_ID" \
  --paths '/*' >/dev/null

echo "Frontend deployment completed successfully."

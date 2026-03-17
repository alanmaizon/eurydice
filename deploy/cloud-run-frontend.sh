#!/bin/bash
set -e

PROJECT_ID="${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="logos-frontend"
IMAGE="gcr.io/$PROJECT_ID/$SERVICE_NAME"
BACKEND_URL="${BACKEND_URL:?Set BACKEND_URL (e.g. https://logos-backend-xxx-uc.a.run.app)}"

# Convert https:// to wss:// for WebSocket URL
WS_URL="${BACKEND_URL/https:\/\//wss://}/ws"

echo "Building and pushing image: $IMAGE"
gcloud builds submit \
  --config frontend/cloudbuild.yaml \
  --substitutions "_IMAGE=$IMAGE,_WS_URL=$WS_URL" \
  ./frontend

echo "Deploying to Cloud Run: $SERVICE_NAME"
gcloud run deploy "$SERVICE_NAME" \
  --image "$IMAGE" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars "NEXT_PUBLIC_WS_URL=$WS_URL" \
  --set-env-vars "NEXT_PUBLIC_APP_NAME=Logos" \
  --memory 256Mi \
  --timeout 60 \
  --concurrency 80

echo "Frontend deployed. URL:"
gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format "value(status.url)"

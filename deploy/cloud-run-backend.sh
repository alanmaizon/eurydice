#!/bin/bash
set -e

PROJECT_ID="${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="logos-backend"
IMAGE="gcr.io/$PROJECT_ID/$SERVICE_NAME"

echo "Building and pushing image: $IMAGE"
gcloud builds submit --tag "$IMAGE" ./backend

echo "Deploying to Cloud Run: $SERVICE_NAME"
# Build env-var string based on which auth mode is configured
ENV_VARS="GEMINI_MODEL=${GEMINI_MODEL:-gemini-live-2.5-flash-native-audio}"
ENV_VARS="${ENV_VARS},MOCK_MODE=${MOCK_MODE:-false}"
ENV_VARS="${ENV_VARS},ALLOWED_ORIGINS=${ALLOWED_ORIGINS:-https://your-frontend-domain.run.app}"

if [[ -n "${GCP_PROJECT_ID:-}" ]]; then
  # Vertex AI mode — uses the Cloud Run service account (ADC), no API key needed
  echo "Auth mode: Vertex AI (project=$PROJECT_ID, region=$REGION)"
  ENV_VARS="${ENV_VARS},GCP_PROJECT_ID=${GCP_PROJECT_ID}"
  ENV_VARS="${ENV_VARS},GCP_REGION=${GCP_REGION:-us-central1}"
elif [[ -n "${GEMINI_API_KEY:-}" ]]; then
  # AI Studio mode
  echo "Auth mode: Google AI Studio (API key)"
  ENV_VARS="${ENV_VARS},GEMINI_API_KEY=${GEMINI_API_KEY}"
else
  echo "WARNING: Neither GCP_PROJECT_ID nor GEMINI_API_KEY is set — deploying in mock mode"
  ENV_VARS="${ENV_VARS},MOCK_MODE=true"
fi

gcloud run deploy "$SERVICE_NAME" \
  --image "$IMAGE" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars "$ENV_VARS" \
  --memory 512Mi \
  --timeout 300 \
  --concurrency 80 \
  --min-instances 0 \
  --max-instances 10

echo "Backend deployed. URL:"
gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format "value(status.url)"

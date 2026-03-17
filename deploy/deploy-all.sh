#!/usr/bin/env bash
# deploy/deploy-all.sh — deploy backend then frontend in one command
#
# Usage:
#   GCP_PROJECT_ID=my-project bash deploy/deploy-all.sh
#
# Optional overrides:
#   GCP_REGION      (default: us-central1)
#   GEMINI_API_KEY  (omit to use Vertex AI ADC)
#   GEMINI_MODEL    (default: gemini-live-2.5-flash-native-audio)
#   MOCK_MODE       (default: false)

set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
REGION="${GCP_REGION:-us-central1}"
BACKEND_SERVICE="logos-backend"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "════════════════════════════════════════"
echo "  LOGOS — full deploy to Cloud Run"
echo "  project : $PROJECT_ID"
echo "  region  : $REGION"
echo "════════════════════════════════════════"

# ── 1. Deploy backend ─────────────────────────────────────────────────────────
echo ""
echo "▶  Step 1/2 — backend"
GCP_PROJECT_ID="$PROJECT_ID" \
GCP_REGION="$REGION" \
bash "$SCRIPT_DIR/cloud-run-backend.sh"

# ── 2. Capture backend URL ────────────────────────────────────────────────────
BACKEND_URL=$(gcloud run services describe "$BACKEND_SERVICE" \
  --region "$REGION" \
  --format "value(status.url)")

echo ""
echo "   backend URL: $BACKEND_URL"

# ── 3. Deploy frontend (bakes BACKEND_URL → wss:// at build time) ─────────────
echo ""
echo "▶  Step 2/2 — frontend"
GCP_PROJECT_ID="$PROJECT_ID" \
GCP_REGION="$REGION" \
BACKEND_URL="$BACKEND_URL" \
bash "$SCRIPT_DIR/cloud-run-frontend.sh"

# ── 4. Summary ────────────────────────────────────────────────────────────────
FRONTEND_URL=$(gcloud run services describe logos-frontend \
  --region "$REGION" \
  --format "value(status.url)")

echo ""
echo "════════════════════════════════════════"
echo "  ✓  Deploy complete"
echo "  Frontend : $FRONTEND_URL"
echo "  Backend  : $BACKEND_URL"
echo "════════════════════════════════════════"

# ── 5. Update ALLOWED_ORIGINS so the backend accepts the frontend ─────────────
echo ""
echo "▶  Updating CORS: ALLOWED_ORIGINS → $FRONTEND_URL"
gcloud run services update "$BACKEND_SERVICE" \
  --region "$REGION" \
  --update-env-vars "ALLOWED_ORIGINS=$FRONTEND_URL" \
  --quiet
echo "   done."

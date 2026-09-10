#!/bin/bash
# ALM Market Voice — IBM Code Engine deployment script (SQLite edition)
#
# Database: SQLite file at /data/alm_market_voice.db inside the container.
# No managed DB needed — $0 database cost.
#
# Prerequisites (already done):
#   - ibmcloud CLI at ~/bin/ibmcloud
#   - code-engine + container-registry plugins installed
#   - Container image built: localhost/alm-market-voice:latest
#
# Usage:
#   export IBM_CLOUD_API_KEY="your-key"
#   export WATSONX_API_KEY="..."
#   export TAVILY_API_KEY="..."
#   ./deploy.sh

set -euo pipefail

export PATH="$HOME/bin:$PATH"

# ── 1. CONFIG ─────────────────────────────────────────────────────────────────
IBM_CLOUD_API_KEY="${IBM_CLOUD_API_KEY:-}"
REGION="us-south"
RESOURCE_GROUP="${RESOURCE_GROUP:-default}"

CR_NAMESPACE="alm-market-voice"
IMAGE_NAME="us.icr.io/${CR_NAMESPACE}/alm-market-voice"
IMAGE_TAG="latest"

CE_PROJECT="alm-market-voice"
CE_APP="alm-market-voice"

WATSONX_API_KEY="${WATSONX_API_KEY:-}"
WATSONX_PROJECT_ID="${WATSONX_PROJECT_ID:-5b815bb7-ba43-4673-a8ef-c44614b24815}"
TAVILY_API_KEY="${TAVILY_API_KEY:-}"
SECRET_KEY="${SECRET_KEY:-$(openssl rand -hex 32)}"

# ── 2. VALIDATE ───────────────────────────────────────────────────────────────
if [[ -z "$IBM_CLOUD_API_KEY" ]]; then
  echo "ERROR: set IBM_CLOUD_API_KEY before running."
  exit 1
fi

# ── 3. LOGIN ──────────────────────────────────────────────────────────────────
echo "=== Logging in to IBM Cloud (${REGION}) ==="
ibmcloud login --apikey "$IBM_CLOUD_API_KEY" -r "$REGION" -g "$RESOURCE_GROUP" -q

# ── 4. CONTAINER REGISTRY ─────────────────────────────────────────────────────
echo ""
echo "=== IBM Container Registry ==="
ibmcloud cr region-set us-south

ibmcloud cr namespace-add "$CR_NAMESPACE" 2>/dev/null \
  && echo "Created namespace: $CR_NAMESPACE" \
  || echo "Namespace already exists — continuing"

echo "Logging Podman into us.icr.io ..."
ibmcloud cr login --client podman 2>/dev/null \
  || ibmcloud iam oauth-tokens --output json \
     | python3 -c "import sys,json; print(json.load(sys.stdin)['iam_token'].split(' ')[1])" \
     | /opt/podman/bin/podman login us.icr.io -u iambearer --password-stdin

# ── 5. PUSH IMAGE ─────────────────────────────────────────────────────────────
echo ""
echo "=== Pushing image ==="
/opt/podman/bin/podman tag localhost/alm-market-voice:latest "${IMAGE_NAME}:${IMAGE_TAG}"
/opt/podman/bin/podman push "${IMAGE_NAME}:${IMAGE_TAG}"
echo "Pushed: ${IMAGE_NAME}:${IMAGE_TAG}"

# ── 6. CODE ENGINE ────────────────────────────────────────────────────────────
echo ""
echo "=== Code Engine project ==="
ibmcloud ce project create --name "$CE_PROJECT" 2>/dev/null \
  && echo "Created project: $CE_PROJECT" \
  || echo "Project already exists — selecting"
ibmcloud ce project select --name "$CE_PROJECT"

# Registry pull secret
ibmcloud ce registry create \
  --name ibm-cr \
  --server us.icr.io \
  --username iamapikey \
  --password "$IBM_CLOUD_API_KEY" \
  2>/dev/null || echo "(registry secret already exists)"

# ── 7. DEPLOY APP ─────────────────────────────────────────────────────────────
echo ""
echo "=== Deploying app (scale-to-zero) ==="

DEPLOY_ARGS=(
  --name "$CE_APP"
  --image "${IMAGE_NAME}:${IMAGE_TAG}"
  --registry-secret ibm-cr
  --port 8000
  --cpu 0.5
  --memory 2G
  --min-scale 0          # scale to zero when idle → free tier
  --max-scale 2
  --scale-down-delay 300 # keep warm for 5 min after last request
  --env DATABASE_URL="sqlite:////data/alm_market_voice.db"
  --env WATSONX_API_KEY="$WATSONX_API_KEY"
  --env WATSONX_PROJECT_ID="$WATSONX_PROJECT_ID"
  --env TAVILY_API_KEY="$TAVILY_API_KEY"
  --env SECRET_KEY="$SECRET_KEY"
  --env CORS_ORIGINS="*"
)

ibmcloud ce application create "${DEPLOY_ARGS[@]}" 2>/dev/null \
  || ibmcloud ce application update \
       --name "$CE_APP" \
       --image "${IMAGE_NAME}:${IMAGE_TAG}" \
       --env DATABASE_URL="sqlite:////data/alm_market_voice.db" \
       --env WATSONX_API_KEY="$WATSONX_API_KEY" \
       --env WATSONX_PROJECT_ID="$WATSONX_PROJECT_ID" \
       --env TAVILY_API_KEY="$TAVILY_API_KEY" \
       --env SECRET_KEY="$SECRET_KEY"

# ── 8. GET URL AND LOCK DOWN CORS ─────────────────────────────────────────────
echo ""
echo "=== Fetching app URL ==="
APP_URL=$(ibmcloud ce application get --name "$CE_APP" --output json \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['status']['url'])")
echo "URL: $APP_URL"

ibmcloud ce application update --name "$CE_APP" --env CORS_ORIGINS="$APP_URL"

# ── 9. SMOKE TEST ─────────────────────────────────────────────────────────────
echo ""
echo "=== Smoke test (waiting 20s for cold start) ==="
sleep 20

HTTP=$(curl -s -o /dev/null -w "%{http_code}" "${APP_URL}/health")
[[ "$HTTP" == "200" ]] \
  && echo "✅ /health → HTTP 200" \
  || echo "⚠️  /health → HTTP $HTTP (may still be warming — check logs)"

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  ALM Market Voice is live!"
echo "  URL : $APP_URL"
echo ""
echo "  First-run steps:"
echo "  1. Seed signals:  curl -X POST ${APP_URL}/api/ingest"
echo "  2. Enrich signals: curl -X POST '${APP_URL}/api/enrich?workers=2'"
echo ""
echo "  NOTE: SQLite is ephemeral on scale-to-zero — data is re-seeded"
echo "  automatically on cold start via the weekly scheduler, or trigger"
echo "  manually with the ingest call above."
echo ""
echo "  To stream logs: ibmcloud ce application logs --name $CE_APP --follow"
echo "════════════════════════════════════════════════════════════"

#!/usr/bin/env bash
# Deploy a PREVIEW (never production) and point the stable dev alias at it.
# Usage: ./deploy-preview.sh   (run from anywhere; it cds to frontend/)
set -euo pipefail
cd "$(dirname "$0")"
ALIAS="crop-yield-dev.vercel.app"
# Previews talk to the DEV Modal API (a superset of production's routes, e.g.
# /calendar/*) instead of the API URL stored for the Preview environment.
DEV_API="${DEV_API:-https://jconrad8--crop-yield-prediction-api-dev-fastapi-app.modal.run}"
URL=$(npx vercel@latest deploy --yes --build-env NEXT_PUBLIC_API_BASE_URL="$DEV_API" | grep -Eo 'https://[a-z0-9-]+\.vercel\.app' | tail -1)
npx vercel@latest alias set "$URL" "$ALIAS"
echo "Preview: https://$ALIAS  (deployment $URL)"

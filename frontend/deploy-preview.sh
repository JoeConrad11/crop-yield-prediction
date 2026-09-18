#!/usr/bin/env bash
# Deploy a PREVIEW (never production) and point the stable dev alias at it.
# Usage: ./deploy-preview.sh   (run from anywhere; it cds to frontend/)
set -euo pipefail
cd "$(dirname "$0")"
ALIAS="crop-yield-dev.vercel.app"
URL=$(npx vercel@latest deploy --yes | grep -Eo 'https://[a-z0-9-]+\.vercel\.app' | tail -1)
npx vercel@latest alias set "$URL" "$ALIAS"
echo "Preview: https://$ALIAS  (deployment $URL)"

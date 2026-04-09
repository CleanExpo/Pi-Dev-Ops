#!/bin/bash
# Pi Dev Ops — Railway Deployment Script
# Usage: RAILWAY_TOKEN=<token> bash scripts/deploy_railway.sh

set -e

if [ -z "$RAILWAY_TOKEN" ]; then
    echo "❌ RAILWAY_TOKEN environment variable not set"
    echo "Get a token from: https://railway.app/account/tokens"
    echo "Then run: RAILWAY_TOKEN=<token> bash scripts/deploy_railway.sh"
    exit 1
fi

echo "════════════════════════════════════════════════════════════"
echo "Pi Dev Ops — Railway Deployment"
echo "════════════════════════════════════════════════════════════"

# Change to project directory
cd "$(dirname "$0")/.."

# Set required environment variables
export TAO_PASSWORD="${TAO_PASSWORD:-$(openssl rand -base64 24)}"
export TAO_SESSION_SECRET="${TAO_SESSION_SECRET:-$(openssl rand -hex 32)}"

echo ""
echo "✓ Environment variables prepared"
echo "  TAO_PASSWORD: ${TAO_PASSWORD:0:8}... (generated)"
echo "  TAO_SESSION_SECRET: ${TAO_SESSION_SECRET:0:8}... (generated)"

# Deploy using Railway CLI
echo ""
echo "Deploying to Railway..."
railway up

echo ""
echo "✓ Deployment started"
echo "Monitor progress: railway logs -f"
echo "View dashboard: railway open"

# Wait for deployment to complete
echo ""
echo "Waiting for deployment to complete (this may take a few minutes)..."
sleep 30

# Get the deployed URL
RAILWAY_URL=$(railway open --json 2>/dev/null || echo "https://your-railway-url.railway.app")

echo ""
echo "════════════════════════════════════════════════════════════"
echo "Deployment Status"
echo "════════════════════════════════════════════════════════════"
echo "Project: pi-ceo"
echo "Status: Check railway logs for details"
echo "URL: $RAILWAY_URL"
echo ""
echo "Next steps:"
echo "1. Set production environment variables in Railway dashboard"
echo "2. Run smoke tests: python scripts/smoke_test.py --url <railway-url> --password <password>"
echo "3. Monitor logs: railway logs -f"
echo "════════════════════════════════════════════════════════════"

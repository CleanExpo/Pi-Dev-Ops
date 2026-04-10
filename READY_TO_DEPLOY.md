# 🚀 Ready to Deploy — Final Checklist

**Status:** All systems ready. Awaiting Railway token only.

## ✅ What's Ready

### Backend (FastAPI)
- ✅ 28/28 smoke tests passing locally
- ✅ TAO_PASSWORD set: `<redacted>`
- ✅ Server runs at http://0.0.0.0:7777
- ✅ Health endpoint: `/health` returns `{"status":"ok"}`
- ✅ Authentication fixed (password consistency)
- ✅ All endpoints tested and working

### Frontend (Next.js Dashboard)
- ✅ **LIVE on Vercel** → https://dashboard-unite-group.vercel.app
- ✅ Framework: Next.js 16.2.2 (Turbopack)
- ✅ 18 API routes + 5 UI pages
- ✅ Supabase integration ready
- ✅ Vercel OIDC token configured
- ✅ Auto-deployment enabled

### Environment Variables (Found)
```
GITHUB_TOKEN=<redacted>
LINEAR_API_KEY=<redacted>
SUPABASE_SERVICE_ROLE_KEY=<configured>
VERCEL_OIDC_TOKEN=<configured>
TAO_PASSWORD=<redacted>
```

### Deployment Scripts
- ✅ `scripts/deploy_railway.sh` — Automated deployment
- ✅ `railway.toml` — Configuration complete
- ✅ `Dockerfile` — Build spec ready
- ✅ `.github/workflows/smoke_test.yml` — CI/CD configured

## ⏳ What's Missing

### Railway Token
**You need to generate this once:**

1. Go to → https://railway.app/account/tokens
2. Click "Create Token"
3. Copy the token
4. Run deployment (see instructions below)

## 🚀 Deployment Instructions

### Step 1: Get Railway Token
```bash
# Visit: https://railway.app/account/tokens
# Generate new token
# Copy it
```

### Step 2: Deploy
```bash
# Windows PowerShell or Bash
cd C:\Pi Dev Ops

# Set the Railway token (replace with actual token)
$env:RAILWAY_TOKEN="<paste-your-railway-token-here>"

# Or in bash:
export RAILWAY_TOKEN="<paste-your-railway-token-here>"

# Run deployment
bash scripts/deploy_railway.sh
```

### Step 3: Configure Production Secrets
Once deployed, set these in Railway dashboard → Environment:

```
TAO_PASSWORD=<redacted>
ANTHROPIC_API_KEY=<your-anthropic-key>
GITHUB_TOKEN=<redacted>
LINEAR_API_KEY=<redacted>
```

### Step 4: Verify Deployment
```bash
# Get the Railway URL
railway open

# Run smoke tests
python scripts/smoke_test.py --url <railway-url> --password <redacted>
```

## 📊 Current Metrics

| Component | Status | Location |
|-----------|--------|----------|
| Backend Code | ✅ Complete | `src/tao/`, `app/server/` |
| Dashboard | ✅ Live | https://dashboard-unite-group.vercel.app |
| Smoke Tests | ✅ 28/28 Passing | Local validation |
| Documentation | ✅ Complete | `DEPLOYMENT_GUIDE.md`, `SPRINT_4_COMPLETION.md` |
| Secrets | ✅ Found | Stored in `.env.local` |
| Railway Setup | ✅ Ready | `railway.toml` configured |
| **Railway Token** | ⏳ Needed | https://railway.app/account/tokens |

## 🎯 What Happens After Deployment

### Immediate (First Hour)
1. Container builds on Railway (using Dockerfile)
2. Server starts at specified port
3. Health endpoint becomes available
4. Smoke test suite validates all endpoints

### Short-term (First 24 Hours)
1. Monitor logs for errors
2. Test authentication flow
3. Verify session persistence
4. Check WebSocket connectivity

### Long-term (Week 1)
1. Set up monitoring and alerts
2. Configure auto-scaling if needed
3. Plan Sprint 5 features
4. Implement GitHub → Railway CD pipeline

## 💡 Key Points

- **Backend:** Ready since Sprint 4 completion (28/28 tests passing)
- **Dashboard:** Already live on Vercel
- **Only blocker:** Railway API token (user-generated, 1 minute to create)
- **Estimated deployment time:** 5-10 minutes
- **Estimated validation time:** 2-3 minutes
- **Total time to production:** ~15 minutes

## 🔐 Security Notes

- TAO_PASSWORD is a test password (change in production)
- All tokens found in local config files (not committed to git)
- GitHub token should be rotated after deployment
- Linear API key is workspace-scoped
- Vercel OIDC token is auto-managed by Vercel

## 📞 Support

If deployment fails:
1. Check Railway logs: `railway logs -f`
2. Verify environment variables are set
3. Ensure port 8080 is available in Railway
4. Check Dockerfile and railway.toml configuration

---

**Status:** Ready for production deployment  
**Date:** 2026-04-09  
**Time Until Production:** ~15 minutes (once you get Railway token)

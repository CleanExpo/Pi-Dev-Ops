---
name: connecting-meta-facebook-instagram
description: Use when connecting or fixing Facebook/Instagram (Meta) OAuth in a web app — Connect button no-ops or errors, "Meta Login for Business config missing", config_id/app mismatch, "Can't load URL / App Domains not included", pages_manage_posts / instagram_content_publish rejected, or repointing Synthex-style social posting to a Meta app you actually control after an ex-employee set it up.
---

# Connecting Meta (Facebook + Instagram) OAuth

## Overview

Meta Page/Instagram *publishing* permissions can no longer be requested with raw OAuth scopes — Meta rejects them unless the request carries a **Facebook Login for Business `config_id`**, and that config_id must belong to the **same app** as the `client_id` you authenticate with. Most "Connect does nothing / Connect errors" bugs are one of a handful of mismatches, not code. This skill is the end-to-end playbook, ordered by what actually blocks you.

**Core principle:** `client_id` (the App ID), the `config_id`, the **App Domains**, and the **redirect URIs** must all belong to and agree within *one* Meta app you control. Get those four aligned, then clear Meta's review gate.

## When to use

- Facebook/Instagram "Connect" button no-ops, or OAuth returns an error.
- Integrations page shows *"Meta Login for Business config missing"* or *"Meta verification and App Review required"*.
- Meta shows *"Can't load URL — the domain of this URL isn't included in the app's domains."*
- `pages_manage_posts` / `instagram_content_publish` get rejected at consent.
- The Meta app was set up by someone who's gone and you need to repoint to an app you own.

## The five gotchas that cost the most time (read first)

1. **config_id is app-scoped.** A Login-for-Business config created on app A will NOT work when your app sends `client_id = B`. Verify the App ID sending the request matches the app the config lives on. (Seen: app sent `909628…`, config was on `131689…` → silent mismatch.)
2. **App Domains ≠ redirect URIs.** Adding the OAuth redirect URI under *Login for Business → Settings* is necessary but not sufficient. The bare domain (e.g. `synthex.social`) must ALSO be in **Settings → Basic → App Domains**, or Meta returns "Can't load URL". Two different fields.
3. **Business Verification + App Review is a separate, multi-day Meta gate.** Even with everything wired correctly, advanced perms (`pages_manage_posts`, `instagram_content_publish`) only work for accounts you don't own after Meta approves App Review + Business Verification. In **Development mode**, an app admin/dev/tester CAN test against their own Page/IG with no review — use that to verify before review lands.
4. **DB credentials beat env vars.** Synthex resolves OAuth creds DB-first (`getPlatformOAuthCredentials` → PlatformOAuthCredential table), then env. Setting `FACEBOOK_CLIENT_ID` in Vercel does nothing if the DB row exists. Update creds via the owner-only UI (**Settings → Integrations → Platform OAuth Credentials**, `POST /api/admin/platform-credentials`, upsert-by-platform), not env.
5. **config_id is read from env only.** `getMetaLoginConfigId` reads `META_BUSINESS_LOGIN_CONFIG_ID` (shared FB+IG fallback) / `FACEBOOK_LOGIN_CONFIG_ID` / `INSTAGRAM_LOGIN_CONFIG_ID` from `process.env`, never the DB. So: creds in DB, config_id in env. One `META_BUSINESS_LOGIN_CONFIG_ID` covers both platforms.

## Playbook

### A. In the Meta app you control (developers.facebook.com)
Owner-only; requires a Facebook account that is admin/dev of the app. If the app was set up by an ex-staffer, use the account/session that owns it, or create a fresh Business-type app and repoint (section D).

1. **Note the App ID** (numeric, ~15–16 digits) shown on the app dashboard. This is your `client_id`. A 32-char hex string is the **App *Secret*** — never the ID; don't confuse them.
2. **Add the product** *Facebook Login for Business* (+ Add Product) if absent.
3. **Login for Business → Settings → Valid OAuth Redirect URIs** — add both, exactly, then Save:
   - `https://<your-domain>/api/auth/callback/facebook`
   - `https://<your-domain>/api/auth/callback/instagram`
4. **Settings → Basic → App Domains** — add `<your-domain>` (bare host, e.g. `synthex.social`) → Save. (Gotcha #2.)
5. **Login for Business → Configurations → Create configuration:**
   - Access token type: **User access token**
   - Permissions: `public_profile, email, pages_show_list, pages_read_engagement, pages_manage_posts, instagram_basic, instagram_content_publish`
   - Create → **copy the Configuration ID** (long number). This is your `config_id`.

### B. Wire the config_id (env)
```bash
echo -n "<CONFIG_ID>" | vercel env add META_BUSINESS_LOGIN_CONFIG_ID production
vercel redeploy <latest-prod-deployment-url>   # env changes need a fresh deploy
```

### C. Point creds at the right app (DB, owner-only UI)
App → **Settings → Integrations → Platform OAuth Credentials** (owner-only). For **Facebook** AND **Instagram** set the **same** values:
- **Client ID** = the numeric App ID (short, all digits)
- **Client Secret** = the 32-char hex App Secret
The user enters the Secret themselves — an agent must never type/hold an app secret. If the Secret is ever pasted into the public Client-ID field, **rotate it** (Settings → Basic → Reset App Secret).

### D. If you must build a fresh app (ownership lost)
Create a Business-type app under a Business Portfolio you own, do section A on it, then section C to repoint. Only the App ID/Secret/config change; redirect URIs and callback code stay the same.

## Verifying (no Meta clicks needed)
Hit the initiation endpoint in an authenticated session and read the JSON — `client_id` and `config_id` are right there:
```
GET https://<your-domain>/api/auth/oauth/facebook?returnTo=/dashboard/platforms
→ {"authorizationUrl":"...client_id=<AppID>...&config_id=<ConfigID>", ...}
```
Then GET that `authorizationUrl` in a browser. Meta's response tells you exactly where you are:
- **Consent/permissions screen** → app + config + domain all agree ✅ (proceed to authorize / App Review).
- **"Can't load URL / App Domains"** → do A.4.
- **Invalid client / config error** → App ID and config_id are on different apps (gotcha #1).

## Common mistakes
| Symptom | Cause | Fix |
|---|---|---|
| "config missing" banner | `META_BUSINESS_LOGIN_CONFIG_ID` unset / not redeployed | B |
| "Can't load URL" | domain not in App Domains | A.4 |
| Invalid client/config | config_id belongs to a different app than client_id | align App ID (C) or config (A.5) |
| Client ID is 32-char hex | App Secret entered in the ID field | C + rotate secret |
| Env var change had no effect | DB row overrides env for creds | update via UI (C), not env |
| Perms greyed / rejected | Advanced Access needs review | test in Dev mode; submit App Review |

## Automation gotcha (browser tooling)
The claude-in-chrome MCP may be paired to a **different, remote browser** than the one the human sees (e.g. a Windows Chrome vs the human's Mac). `list_connected_browsers` / `switch_browser` reveal this. computer-use can *see* a local browser but browsers are read-only tier (no clicks/typing). Symptom: you type into one browser, the human's keystrokes land in another → "it's in" but the field is empty on your side. Confirm which browser you're driving before a multi-step, cross-actor flow, and prefer the JSON-endpoint verification above over screen-scraping.

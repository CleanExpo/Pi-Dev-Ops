---
name: deployment
description: Deployment constraints and runtime behaviour for Railway (backend) and Vercel (frontend) — proxy config, redirects, Telegram, SSE limits, and model routing.
---

# Deployment Patterns

## When to apply

Apply whenever touching Railway config, Vercel SSE routes, HTTP fetchers, Telegram notifications, or per-phase model selection.

## Rules

- Railway terminates TLS and proxies all requests. Do NOT add `TrustedHostMiddleware` restricting to `127.0.0.1` — it blocks all cloud traffic. Use `ALLOWED_ORIGINS` for CORS control instead.
- Anthropic docs URLs (`docs.claude.com`) redirect to `platform.claude.com` and `code.claude.com`. Any `httpx` fetcher that hits Anthropic docs must set `follow_redirects=True` or requests will return 3xx and no content.
- Telegram push from any sandboxed Python environment needs only `TELEGRAM_BOT_TOKEN` + a `chat_id`. The full `python-telegram-bot` package is NOT required — `urllib` + a POST to `api.telegram.org/bot{token}/sendMessage` is sufficient. See `scripts/send_telegram.py`.
- Vercel hard-limits SSE responses to 300 seconds. The analysis pipeline must abort in-flight SDK calls at 240 s and send a partial done event before the platform cuts the connection. Use `AbortController` — a budget timer alone cannot stop a running SDK call.
- Use per-phase model routing to stay within the 300 s Vercel SSE window: `haiku-3-5` for inventory and summarisation phases (1, 2, 4) and `sonnet` for intelligence phases (3, 5, 6, 7). This cuts total analysis runtime from ~350 s to ~200 s.

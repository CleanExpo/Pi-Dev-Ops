# Mission Control Model Fabric

Status: implementation branch

Mission Control remains the authority and user-facing operating system. OmniRoute is used only as an internal model-routing engine. Slack, Telegram, Margot, context/memory, approvals, projects, and Mission Control UI remain owned by Pi-Dev-Ops.

## Invariants

- No Ollama or Gemma route for founder/Margot traffic.
- Founder conversations route only through an allowlisted model-fabric lane.
- Free providers are not trusted by default; privacy/ToS suitability is a separate gate from cost.
- Mission Control owns routing policy and observability.
- OmniRoute is replaceable infrastructure behind a narrow adapter.
- Paid/high-trust fallback remains available when free capacity or quality is insufficient.
- Model selection evidence (provider, model, lane, latency, health/fallback state) is visible in `/control/model`.

## Lanes

- `founder-chat`: quality-first, no exploration, Slack + Telegram + Margot.
- `founder-critical`: strongest trusted model only; strategy, legal, money, production risk.
- `internal-work`: trusted-free-first.
- `research`: broader provider pool, public/non-confidential input only.
- `coding`: coding-optimised pool.
- `background`: cheapest approved pool.
- `emergency`: paid/high-trust escape hatch.

## Deployment

Pi-CEO owns the adapter. OmniRoute may run locally inside the Pi-CEO host or at a private Tailnet URL. The adapter is configured with `OMNIROUTE_BASE_URL`, `OMNIROUTE_API_KEY`, and `OMNIROUTE_ENABLED=1`. If unavailable, founder lanes fail over to the existing high-trust provider path, never to a banned local model.

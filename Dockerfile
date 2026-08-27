# Pi CEO — FastAPI server (Railway/Fly deployment)
# Build from project root: docker build -t pi-ceo .

FROM python:3.12-slim

# System deps: git (clone/push), Node.js 24 LTS (Claude CLI + OmniRoute), and
# build tooling for better-sqlite3 if a prebuilt binary is unavailable.
# OmniRoute's supported secure runtime floor is >=22.22.2 or >=24; pinning the
# major to Node 24 avoids an ambiguous/older Node 22 patch from NodeSource.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates build-essential \
    && curl -fsSL https://deb.nodesource.com/setup_24.x -o /tmp/nodesource_setup.sh \
    && bash /tmp/nodesource_setup.sh \
    && rm -f /tmp/nodesource_setup.sh \
    && apt-get install -y --no-install-recommends nodejs \
    && node --version | grep -Eq '^v24\.' \
    && npm --version \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Claude remains the high-trust escape hatch. OmniRoute is pinned to the latest
# published npm version reviewed for the Mission Control model-fabric build.
RUN npm install -g @anthropic-ai/claude-code omniroute@3.8.49 \
    && omniroute --version

# Create non-root user — claude_agent_sdk refuses --dangerously-skip-permissions
# when invoked as root, so the server must run as an unprivileged user.
RUN useradd -m -u 1001 pidev

# Python dependencies
WORKDIR /pi-ceo
COPY app/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY app/server/ ./app/server/

# TAO engine (imported by sessions.py via sys.path manipulation)
COPY src/ ./src/

# RA-1869 — Wave-4/5 swarm orchestrator + bots.
COPY swarm/ ./swarm/

# Committed config / skills
COPY config/harness/ ./config/harness/
COPY skills/ ./skills/

# Board governance corpus
COPY docs/governance/board-meetings/ ./docs/governance/board-meetings/

# Utility scripts
COPY scripts/ ./scripts/

# Packaged Margot FastMCP runtime.
COPY vendor/margot-deep-research/ ./vendor/margot-deep-research/

# Runtime directories. OmniRoute state is intentionally local/ephemeral here:
# Mission Control rehydrates approved providers on each deploy and does not use
# OmniRoute as its source of memory or authority.
RUN mkdir -p app/workspaces app/logs/.sessions app/data .harness /pi-ceo/.omniroute && \
    chown -R pidev:pidev /pi-ceo

USER pidev

# Railway uses PORT env var; TAO reads TAO_HOST/TAO_PORT
ENV TAO_HOST=0.0.0.0
ENV TAO_PORT=8080
ENV TAO_USE_AGENT_SDK=1
ENV PYTHONPATH=/pi-ceo
ENV MARGOT_SERVER_PATH=/pi-ceo/vendor/margot-deep-research/server.py

# Mission Control Model Fabric — local sidecar, not a public dashboard.
ENV OMNIROUTE_ENABLED=1
ENV OMNIROUTE_BASE_URL=http://127.0.0.1:20128
ENV OMNIROUTE_ROLES=margot.casual
ENV OMNIROUTE_STRENGTHEN_MARGOT=smart
ENV DATA_DIR=/pi-ceo/.omniroute
ENV REQUIRE_API_KEY=false
ENV HOSTNAME=127.0.0.1

# OM-1: 15-move lookahead planner (override per-deploy via Railway env).
ENV TAO_OM1_ENABLED=1
ENV TAO_PLANNER_MAX_REPLANS=2

EXPOSE 8080

WORKDIR /pi-ceo
CMD ["python", "scripts/runtime_model_guard.py"]

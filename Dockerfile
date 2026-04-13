# Pi CEO — FastAPI server (Railway/Fly deployment)
# Build from project root: docker build -t pi-ceo .

FROM python:3.12-slim

# System deps: git (clone/push), Node.js (claude CLI)
RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install claude CLI (uses ANTHROPIC_API_KEY at runtime)
RUN npm install -g @anthropic-ai/claude-code

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

# Harness data: lessons seed, TAO config, skills
COPY .harness/ ./.harness/
COPY skills/ ./skills/

# Utility scripts (analyse_lessons, smoke_test, fallback_dryrun, etc.)
COPY scripts/ ./scripts/

# Runtime directories — owned by pidev so the server can write to them
RUN mkdir -p app/workspaces app/logs/.sessions app/data && \
    chown -R pidev:pidev /pi-ceo

USER pidev

# Railway uses PORT env var; TAO reads TAO_HOST/TAO_PORT
ENV TAO_HOST=0.0.0.0
ENV TAO_PORT=8080
ENV PYTHONPATH=/pi-ceo

EXPOSE 8080

# Set working dir so relative paths in config.py resolve correctly
WORKDIR /pi-ceo
CMD ["uvicorn", "app.server.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]

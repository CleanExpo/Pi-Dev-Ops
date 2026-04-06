FROM python:3.12-slim

# System deps: git for clone/push, curl + Node.js for claude CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install claude CLI (non-interactive mode works with ANTHROPIC_API_KEY)
RUN npm install -g @anthropic-ai/claude-code

# Python dependencies
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY server/ ./server/

# Workspaces and logs dirs (ephemeral but need to exist)
RUN mkdir -p workspaces logs

# Expose Railway-standard port
ENV TAO_HOST=0.0.0.0
ENV TAO_PORT=8080
EXPOSE 8080

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]

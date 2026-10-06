#!/usr/bin/env bash
# sandcastle-bootstrap.sh — RA-1856 (Wave 5)
#
# Installs @ai-hero/sandcastle@0.12.0 (exact pin) into a target business repo,
# runs its `sandcastle init` bin with Pi-CEO standard preferences, and copies
# Pi-Dev-Ops's scripts/sandcastle_run.mts into .sandcastle/ (UNI-2926):
#   - agent: claude-code
#   - sandbox: docker
#   - issue tracker: github-issues
#   - template: parallel-planner-with-review
#
# Never call bare `npx sandcastle`: the unscoped npm name is an unrelated
# package. The bin is only reached via `npx --no-install` after the local
# install. @ai-hero/sandcastle has no `run` command; jobs run through
# .sandcastle/sandcastle_run.mts, which calls the JS `run()` API.
#
# Usage:
#   ./scripts/sandcastle-bootstrap.sh <target_repo_path>
#
# Example:
#   ./scripts/sandcastle-bootstrap.sh /tmp/pi-ceo-workspaces/ra-1839-ios-fix
#
# Idempotent: re-run is safe. Won't re-init if .sandcastle/ already exists.
# Won't reinstall if @ai-hero/sandcastle 0.12.0 is already in package.json.
#
# Pre-flight checks:
#   - Docker installed
#   - Node 22+ available
#   - npm available
#   - Target dir exists + contains a package.json (creates one if missing)
#   - GH_TOKEN env var present (sandcastle backlog manager needs it)

set -euo pipefail

SANDCASTLE_VERSION="0.12.0"
TSX_VERSION="4.23.15"
RUNNER_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sandcastle_run.mts"

# ── Argument parsing ────────────────────────────────────────────────────────
TARGET="${1:-}"
if [[ -z "$TARGET" ]]; then
  echo "❌ usage: $0 <target_repo_path>" >&2
  exit 64
fi
if [[ ! -d "$TARGET" ]]; then
  echo "❌ target not found: $TARGET" >&2
  exit 66
fi

cd "$TARGET"
echo "→ working in: $(pwd)"

# ── Pre-flight: Docker ──────────────────────────────────────────────────────
if ! command -v docker >/dev/null 2>&1; then
  echo "❌ docker not found in PATH — install Docker Desktop or Colima first" >&2
  exit 69
fi
DOCKER_VERSION="$(docker --version 2>/dev/null | head -1 || echo "unknown")"
echo "  docker: $DOCKER_VERSION"

if ! docker info >/dev/null 2>&1; then
  echo "⚠ docker daemon not running — sandcastle init will succeed, but"
  echo "  'docker build' (final step) will fail. Start Docker Desktop and re-run."
  DOCKER_RUNNING=false
else
  DOCKER_RUNNING=true
fi

# ── Pre-flight: Node + npm ──────────────────────────────────────────────────
if ! command -v node >/dev/null 2>&1; then
  echo "❌ node not found in PATH" >&2
  exit 69
fi
NODE_VERSION="$(node --version)"
NODE_MAJOR="${NODE_VERSION#v}"
NODE_MAJOR="${NODE_MAJOR%%.*}"
if [[ "$NODE_MAJOR" -lt 22 ]]; then
  echo "❌ node $NODE_VERSION too old; sandcastle requires Node 22+" >&2
  exit 70
fi
echo "  node:   $NODE_VERSION"
echo "  npm:    $(npm --version)"

# ── Pre-flight: package.json ────────────────────────────────────────────────
if [[ ! -f package.json ]]; then
  echo "→ no package.json — creating minimal one"
  cat > package.json <<'EOF'
{
  "name": "sandcastle-host",
  "version": "0.0.0",
  "private": true,
  "scripts": {
    "sandcastle": "tsx .sandcastle/main.mts"
  },
  "devDependencies": {}
}
EOF
fi

# ── Pre-flight: GH_TOKEN ────────────────────────────────────────────────────
if [[ -z "${GH_TOKEN:-}" ]] && [[ -z "${GITHUB_TOKEN:-}" ]]; then
  echo "⚠ neither GH_TOKEN nor GITHUB_TOKEN set"
  echo "  Sandcastle backlog manager (GitHub issues) won't authenticate."
  echo "  Set one before running 'npm run sandcastle'."
fi

# ── Step 1: install @ai-hero/sandcastle ─────────────────────────────────────
installed_version() {
  node -p "require('./node_modules/$1/package.json').version" 2>/dev/null || true
}
deps_installed() {
  [[ "$(installed_version @ai-hero/sandcastle)" == "$SANDCASTLE_VERSION" ]] \
    && [[ "$(installed_version tsx)" == "$TSX_VERSION" ]] \
    && [[ -x node_modules/.bin/tsx ]]
}
if grep -q "\"@ai-hero/sandcastle\": \"$SANDCASTLE_VERSION\"" package.json 2>/dev/null \
   && grep -q "\"tsx\": \"$TSX_VERSION\"" package.json 2>/dev/null \
   && deps_installed; then
  echo "→ @ai-hero/sandcastle@$SANDCASTLE_VERSION + tsx@$TSX_VERSION already installed — skipping install"
else
  echo "→ installing @ai-hero/sandcastle@$SANDCASTLE_VERSION + tsx@$TSX_VERSION"
  npm install --save-dev --save-exact "@ai-hero/sandcastle@$SANDCASTLE_VERSION" "tsx@$TSX_VERSION"
fi
if ! deps_installed; then
  echo "✗ node_modules lacks @ai-hero/sandcastle@$SANDCASTLE_VERSION or tsx@$TSX_VERSION (with .bin/tsx) after install" >&2
  exit 1
fi

# ── Step 2: sandcastle init ─────────────────────────────────────────────────
if [[ -d .sandcastle ]]; then
  echo "→ .sandcastle/ already exists — skipping init"
  echo "  (delete .sandcastle/ to re-init from scratch)"
else
  echo "→ running 'sandcastle init' (local @ai-hero/sandcastle bin) with Pi-CEO standard preferences"
  # Flags verified against `sandcastle init --help` in 0.12.0. Step 5 builds
  # the image, so init does not.
  npx --no-install sandcastle init \
    --agent claude-code \
    --sandbox docker \
    --issue-tracker github-issues \
    --template parallel-planner-with-review \
    --create-label false \
    --build-image false \
    --install-template-deps true \
    || {
      echo "⚠ 'sandcastle init' non-interactive mode failed."
      echo "  Run interactively:  npx --no-install sandcastle init --wizard"
      echo "  Pi-CEO standard answers:"
      echo "    Agent:         Claude Code"
      echo "    Sandbox:       Docker"
      echo "    Issue tracker: GitHub Issues"
      echo "    Template:      parallel-planner-with-review"
      exit 1
    }
fi

# ── Step 2b: install the Pi-CEO runner (UNI-2926) ───────────────────────────
# Copied on every run so the target always has the current runner. It must
# live inside the target: it imports @ai-hero/sandcastle from node_modules here.
if [[ -f "$RUNNER_SRC" ]]; then
  cp "$RUNNER_SRC" .sandcastle/sandcastle_run.mts
  echo "→ installed .sandcastle/sandcastle_run.mts"
else
  echo "❌ runner not found: $RUNNER_SRC" >&2
  exit 1
fi

# ── Step 3: append Pi-CEO Dockerfile addendum ───────────────────────────────
if grep -q "Pi-CEO addendum" .sandcastle/Dockerfile 2>/dev/null; then
  echo "→ Pi-CEO Dockerfile addendum already present"
else
  echo "→ appending Pi-CEO Dockerfile addendum (Linear MCP CLI + git config)"
  cat >> .sandcastle/Dockerfile <<'EOF'

# ── Pi-CEO addendum (RA-1856) ───────────────────────────────────────────────
# Linear CLI for autonomous ticket triage from inside the sandbox
RUN npm install -g @linear/cli 2>/dev/null || echo "warn: @linear/cli unavailable; agent will use HTTP API directly"

# Pi-CEO git config — commits attribute to "Pi-CEO Sandcastle <ai+sandcastle@unite-group.com.au>"
RUN git config --global user.name "Pi-CEO Sandcastle" && \
    git config --global user.email "ai+sandcastle@unite-group.com.au" && \
    git config --global init.defaultBranch main && \
    git config --global pull.rebase false

# Pi-CEO standard agent shell hardening
RUN echo 'export NODE_NO_WARNINGS=1' >> /home/agent/.bashrc && \
    echo 'export TAO_SANDCASTLE_RUN=1' >> /home/agent/.bashrc
EOF
fi

# ── Step 4: ensure .gitignore covers Sandcastle outputs ─────────────────────
if [[ -f .gitignore ]]; then
  if ! grep -q "^\.sandcastle/\.env" .gitignore 2>/dev/null; then
    echo "→ adding .sandcastle/.env to .gitignore (NEVER commit secrets)"
    cat >> .gitignore <<'EOF'

# Sandcastle (RA-1856) — never commit env values or session captures
.sandcastle/.env
.sandcastle/logs/
.sandcastle/sessions/
EOF
  fi
else
  echo "→ creating .gitignore with Sandcastle exclusions"
  cat > .gitignore <<'EOF'
# Sandcastle (RA-1856) — never commit env values or session captures
.sandcastle/.env
.sandcastle/logs/
.sandcastle/sessions/
EOF
fi

# ── Step 5: build the Docker image (only if daemon up) ──────────────────────
if [[ "$DOCKER_RUNNING" == "true" ]]; then
  echo "→ building default Sandcastle Docker image (this may take ~2 min)"
  cd .sandcastle
  IMAGE_TAG="sandcastle-$(basename "$TARGET")"
  docker build -t "$IMAGE_TAG" -f Dockerfile . || {
    echo "❌ docker build failed — review .sandcastle/Dockerfile"
    exit 1
  }
  echo "  ✅ image built: $IMAGE_TAG"
  cd "$TARGET"
else
  echo "→ skipping docker build (daemon not running)"
  echo "  Run when ready:  cd $TARGET/.sandcastle && docker build -t sandcastle-$(basename "$TARGET") ."
fi

# ── Done ────────────────────────────────────────────────────────────────────
echo ""
echo "✅ Sandcastle bootstrapped at $TARGET"
echo ""
echo "Next steps for the operator:"
echo "  1. Set required env vars in .sandcastle/.env (use .sandcastle/.env.example as template)"
echo "     → ANTHROPIC_API_KEY (or claude subscription per .sandcastle docs)"
echo "     → GH_TOKEN  (for GitHub-issues backlog manager)"
echo "  2. Add the 'sandcastle:high-isolation' label to a target GitHub issue"
echo "  3. From this repo:  npx --no-install tsx .sandcastle/sandcastle_run.mts <config.json>"
echo "  4. Or trigger via Pi-CEO autonomy.py once Wave 5 #6 (run_build branch point) ships"

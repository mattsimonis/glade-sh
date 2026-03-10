.PHONY: up down restart build logs shell deploy-web ps setup

# Load .env if present — provides HOST, DOMAIN, DEV_DIR, ROOST_DIR
ifneq (,$(wildcard .env))
  include .env
  export
endif

HOST    ?= mac-mini
DOMAIN  ?= ai.home

# ── First-time setup ──────────────────────────────────────────────────────────

# Run once on a new machine: creates the Docker network, starts services.
setup:
	@echo "→ Creating Docker network 'shared_web' (safe to ignore if it already exists)..."
	docker network create shared_web 2>/dev/null || true
	@echo "→ Starting services..."
	docker compose up -d
	@echo ""
	@echo "✓ Done. Visit https://$(DOMAIN)"

# ── Daily operations ──────────────────────────────────────────────────────────

# Start all services (or bring them back up after a restart)
up:
	docker compose up -d

# Stop all services
down:
	docker compose down

# Restart the ttyd container — picks up api.py changes without a rebuild
restart:
	docker compose restart ttyd

# Full rebuild — only needed after Dockerfile, entrypoint.sh, or config/ changes
build:
	docker compose build ttyd && docker compose up -d

# Tail logs for all services (Ctrl-C to stop)
logs:
	docker compose logs -f

# Open a Zsh shell inside the running container
shell:
	docker compose exec ttyd zsh

# Show running container status
ps:
	docker compose ps

# ── Remote deploy (only needed when not running directly on the host) ─────────

# Copy web/index.html to the host when the web service can't mount ./web directly.
# Override host: make deploy-web HOST=other-machine
deploy-web:
	scp web/index.html $(HOST):~/.roost/web/index.html

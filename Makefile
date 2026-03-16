.PHONY: up down restart build logs shell deploy-web ps setup dev test test-cov test-e2e

# Load .env if present — provides HOST, DOMAIN, DEV_DIR, GLADE_DIR
ifneq (,$(wildcard .env))
  include .env
  export
endif

HOST    ?= mac-mini
DOMAIN  ?= glade.home

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
	docker compose build --build-arg BUILD_DATE=$(shell date +%Y%m%d%H%M%S) ttyd && docker compose up -d

# Tail logs for all services (Ctrl-C to stop)
logs:
	docker compose logs -f

# Open a Zsh shell inside the running container
shell:
	docker compose exec ttyd zsh

# Show running container status
ps:
	docker compose ps

# ── Local dev (edit index.html and see changes live) ─────────────────────────

# Opens an SSH tunnel to casper and starts the dev server on http://localhost:3000.
# Edit web/index.html and refresh — no deploy step needed.
dev:
	node bin/dev-server.js

# ── Remote deploy (only needed when not running directly on the host) ─────────

# Copy web/index.html to the host when the web service can't mount ./web directly.
# Override host: make deploy-web HOST=other-machine
deploy-web:
	scp web/index.html $(HOST):~/.glade/web/index.html

# ── Testing ────────────────────────────────────────────────────────────────────

# Run API unit tests
test:
	python3 -m pytest tests/api/ -v --tb=short

# Run API tests with coverage report
test-cov:
	python3 -m pytest tests/api/ -v --cov=api --cov-report=term-missing --tb=short

# Run Playwright E2E tests (requires a running Glade instance at BASE_URL)
test-e2e:
	cd tests/e2e && npx playwright test

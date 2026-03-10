# Contributing to Roost

## What's most useful right now

- **Screenshots and GIFs** — the README has a placeholder for visuals. If you run Roost and want to share a screenshot or screen recording, open a PR adding them to `assets/`.
- **Bug reports** — use the issue template. Include your OS, Docker version, and the output of `docker compose logs`.
- **Feature requests** — use the issue template. Describe the use case, not just the feature.

## Making code changes

### Prerequisites

- Docker Desktop
- Python 3.x (for running the API outside a container, if needed)
- A working Roost instance to test against

### Local development

The repo uses bind mounts — the containers read files directly from the repo. So edits are live without rebuilding.

```bash
git clone https://github.com/mattsimonis/roost
cd roost
cp .env.example .env
# edit .env with your settings
make setup
```

| What changed | How to apply |
|---|---|
| `web/index.html` | Refresh browser |
| `api/api.py` | `make restart` |
| `Dockerfile`, `config/` | `make build` |
| `docker-compose.yml` | `make down && make up` |

### Code style

- **Python** (`api/api.py`): stdlib only. No third-party packages. Match the existing style — handlers, routing, and response helpers follow an established pattern.
- **JavaScript** (`web/index.html`): vanilla JS, no build step. Keep CSS variables in the Catppuccin palette.
- **Shell scripts**: POSIX-compatible where possible.

### Submitting a PR

1. Fork the repo and create a branch from `main`.
2. Make your change. Test it against a live instance.
3. Keep PRs focused — one thing per PR.
4. Describe *what* and *why* in the PR description, not just *what*.

## Reporting security issues

Don't open a public issue. Email directly instead (see the repo owner's GitHub profile).

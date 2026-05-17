# Peanut Setup

Peanut uses the same provider families as the reference assistant:

- Trello for task data
- Google AI Studio / Gemini for prioritization
- Telegram for briefings and on-demand updates
- Gmail OAuth2 read-only access for optional email context

This repository is public. Store real values only in `.env.local`, GitHub
repository secrets, or the gitignored Nature secrets file.

## Local Environment

```bash
cp .env.example .env.local
```

If migrating from the reference app, copy its local environment file after the
Peanut `.gitignore` exists:

```bash
cp /path/to/reference-assistant/.env.local .env.local
git status --short --ignored .env.local
```

## Gmail OAuth

Run the helper after setting `GMAIL_CLIENT_ID` and `GMAIL_CLIENT_SECRET`:

```bash
uv run python -m app.gmail_auth
```

Add the returned refresh token to `.env.local`. Keep Gmail scope read-only.

## Cereal Deployment Secrets

Cluster secrets are managed in `~/dv/Nature`, not in this repo:

```bash
cd ~/dv/Nature
./scripts/secrets.sh create peanut-secrets -n peanut --type Opaque
./scripts/secrets.sh push peanut-secrets
```

Do not commit `~/dv/Nature/secrets.yaml`.

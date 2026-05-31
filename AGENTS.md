# Peanut - Agent Context

## Deployment Cluster

Peanut deploys to the Cereal Kubernetes cluster via the Nature GitOps repository.

- Local cluster-control repository path: `~/dv/Nature`
- App manifests: `~/dv/Nature/kubernetes/peanut`
- Flux Kustomization: `~/dv/Nature/kubernetes/flux/peanut.yaml`
- Flux aggregator: `~/dv/Nature/kubernetes/flux/kustomization.yaml`

## Security Notes

- This is a public repository.
- Never commit `.env.local`, OAuth tokens, API keys, kubeconfigs, plaintext
  Kubernetes Secrets, or local data files.
- Use `~/dv/Nature/scripts/secrets.sh` and the gitignored
  `~/dv/Nature/secrets.yaml` for Kubernetes credentials.

## Debugging Sent Telegram Output

- Peanut appends every successfully sent Telegram message to
  `/data/telegram_messages.jsonl` by default.
- Each JSONL entry includes `timestamp`, `chat_id`, and full `text`.
- The path is configurable with `TELEGRAM_MESSAGE_LOG_PATH`.
- Treat this as local app state: it may contain personal/private output and
  must not be committed.

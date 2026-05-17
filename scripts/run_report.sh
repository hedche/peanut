#!/bin/bash
# Run a one-shot Peanut briefing locally
# Usage: ./scripts/run_report.sh

set -e

cd "$(dirname "$0")/.."

echo "🥜 Running Peanut personal assistant briefing..."
uv run python -m app.run

echo "✅ Briefing complete!"

#!/usr/bin/env bash
# Runs the Campaign QA skill on the example campaign with Claude Code, then scores it.
# This uses your Claude Code plan or API credits. Run it from anywhere.
set -euo pipefail

repo="$(cd "$(dirname "$0")/../.." && pwd)"
out="${1:-$repo/evals/campaign-qa/results/review-$(date +%Y%m%d-%H%M%S).md}"
mkdir -p "$(dirname "$out")"
out="$(cd "$(dirname "$out")" && pwd)/$(basename "$out")"   # absolute, before the cd below

prompt='Use the campaign-qa skill to check the campaign in examples/tidewater-spring-sale.
After the report, list only your judgment calls (not the script findings) as a JSON array
in a ```json block. Each item: {"asset": "<path relative to the campaign folder>",
"line": <number>, "quote": "<exact words>", "why": "<one sentence>"}.'

cd "$repo"
claude -p "$prompt" < /dev/null > "$out"
echo "Review saved to $out"
python3 "$repo/evals/campaign-qa/score.py" --review "$out"

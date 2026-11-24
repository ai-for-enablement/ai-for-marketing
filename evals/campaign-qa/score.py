#!/usr/bin/env python3
"""Scores Campaign QA against the planted mistakes in expected.toml.

  score.py                      score the script (free, no AI)
  score.py --review REVIEW.md   also score an AI review's judgment calls

The review file is the skill's output with its judgment calls as a JSON list in a
```json block (run_review.sh asks for this), or a plain .json file. Each item needs
"asset" and "quote"; "why" is optional.

Exit code: 0 = every planted mistake caught and no unexpected script findings, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "skills" / "campaign-qa" / "scripts"))
import campaign_qa  # noqa: E402  # pyright: ignore[reportMissingImports]


def score_script(exp: dict) -> bool:
    want = Counter((s["check"], s["asset"], s.get("line")) for s in exp["script"])
    rep = campaign_qa.run(REPO / exp["campaign"])
    got = Counter((f.check, f.asset, f.line) for f in rep.findings)
    missed, extra = want - got, got - want
    print(f"Script: caught {sum((want & got).values())} of {sum(want.values())} planted findings, "
          f"{sum(extra.values())} unexpected.")
    notes = {(s["check"], s["asset"], s.get("line")): s.get("note", "") for s in exp["script"]}
    for k in missed.elements():
        print(f"  MISSED  {k[0]} {k[1]}:{k[2]}  {notes[k]}")
    for k in extra.elements():
        print(f"  EXTRA   {k[0]} {k[1]}:{k[2]}")
    return not missed and not extra


def load_review(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return json.loads(text)
    blocks = re.findall(r"```json\s*\n(.*?)```", text, re.S)
    if not blocks:
        raise SystemExit(f"{path}: no ```json block found")
    return json.loads(blocks[-1])


def score_review(exp: dict, items: list[dict]) -> bool:
    used: set[int] = set()
    caught = []
    for j in exp["judgment"]:
        for i, it in enumerate(items):
            if i in used or it.get("asset", "").lstrip("./") != j["asset"]:
                continue
            text = f"{it.get('quote', '')} {it.get('why', '')}".lower()
            if any(k.lower() in text for k in j["keywords"]):
                used.add(i)
                caught.append(j["id"])
                break
    total = len(exp["judgment"])
    print(f"Judgment: caught {len(caught)} of {total} planted mistakes; "
          f"{len(items) - len(used)} other findings (read them: some may be fair).")
    for j in exp["judgment"]:
        if j["id"] not in caught:
            print(f"  MISSED  {j['id']} {j['asset']}  {j['note']}")
    for i, it in enumerate(items):
        if i not in used:
            print(f"  OTHER   {it.get('asset')}:{it.get('line', '')}  {it.get('quote', '')[:80]}")
    return len(caught) == total


def main() -> int:
    ap = argparse.ArgumentParser(description="Score Campaign QA against expected.toml.")
    ap.add_argument("--review", type=Path, help="AI review output to score")
    a = ap.parse_args()
    exp = tomllib.loads((HERE / "expected.toml").read_text(encoding="utf-8"))
    ok = score_script(exp)
    if a.review:
        ok = score_review(exp, load_review(a.review)) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

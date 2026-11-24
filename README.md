# AI for Marketing

Claude Code skills for marketing teams. Every skill here comes with a sample campaign full of planted mistakes and a score showing how many it catches, so you can see what it does before you trust it with a real launch.

Install only the skills you want. Each one is a plain folder you copy.

## Skills

| Skill | What it does | Tested on the sample campaign |
|---|---|---|
| [Campaign QA](skills/campaign-qa/) | Checks a campaign before launch: links, UTM tags, promo codes, dates, landing-page tracking and forms, then reads the copy for offer drift, unsupported claims and off-brand tone. | Script: 22 of 22 planted findings, no false alarms. AI review: 10 of 10 judgment calls in each of the last two runs ([evals](evals/campaign-qa/)). |

More are on the way.

## Install a skill

You need [Claude Code](https://claude.com/claude-code) and, for skills with scripts, Python 3.11 or newer. On a Mac, `python3 --version` tells you which one you have. If it says 3.9, install a newer one from [python.org](https://www.python.org/downloads/) or with `brew install python`.

1. Download this repo (green **Code** button, then **Download ZIP**), or clone it.
2. Copy the skill's folder into your skills folder:

   ```bash
   mkdir -p ~/.claude/skills
   cp -R skills/campaign-qa ~/.claude/skills/
   ```

   You should now have `~/.claude/skills/campaign-qa/SKILL.md`.

   To share a skill with one project's team instead, copy it into that project's `.claude/skills/` folder.
3. Start Claude Code and ask for it in plain words, like "QA the campaign in this folder."

To update a skill, copy the new folder over the old one.

## Try it on the sample campaign

`examples/tidewater-spring-sale` is a spring sale for Tidewater Bikes, a made-up shop. Its emails, social posts and landing page are full of planted mistakes, from a staging link to a promise of free shipping nobody approved. The answer key lists 22 findings the script should report and 10 problems that need a careful read.

```bash
python3 skills/campaign-qa/scripts/campaign_qa.py examples/tidewater-spring-sale
```

Or open Claude Code in this folder and ask it to QA the example campaign. The repo's `.claude/skills` folder points at the skills here, so they work without installing.

## How skills here are built

- **Scripts for anything with a right answer.** Whether a UTM tag is missing doesn't need AI. A script checks it the same way every time, for free.
- **AI for anything that needs reading.** Tone, offer scope and claims need judgment, so the skill asks Claude to read every asset and say which findings are its judgment.
- **Every skill is tested.** Each one has a sample with planted mistakes, an answer key in `evals/`, and a score. Tests in `tests/` check the scripts.
- **Made-up data only.** The examples use fictional companies.

## Check the scores yourself

```bash
python3 evals/campaign-qa/score.py           # the script, free
evals/campaign-qa/run_review.sh               # the AI review; uses your Claude Code plan
python3 -m unittest discover tests            # unit tests
```

## License

MIT. See [LICENSE](LICENSE).

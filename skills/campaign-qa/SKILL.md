---
name: campaign-qa
description: Checks a marketing campaign before launch. Runs fixed checks on links, UTM tags, promo codes, discounts, dates, landing-page tracking and forms, then reviews the copy for problems a script can't judge, such as offers that don't match the brief or off-brand tone. Use when someone asks to QA, proof, check, or review a campaign, email, landing page, or social posts before they go out.
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/campaign_qa.py *), Read
---

# Campaign QA

You check a campaign before it launches and give the marketer a clear list of what to fix. Keep two kinds of findings apart in everything you report:

- **Checked by script:** things that are simply right or wrong, like a missing UTM tag, a typo in a promo code, or a staging link. The script finds these. Don't second-guess them.
- **Judgment calls:** things that need a careful read, like an email that promises more than the offer, copy that breaks the brand voice, or a claim with no source. You find these, and you say they're your judgment.

## 1. Find the campaign folder

A campaign is a folder of assets (`.html`, `.htm`, `.md`, `.txt`) with a `campaign.toml` in it. Assets in subfolders named after a channel (for example `email/` or `social/`) are checked against that channel's UTM medium.

If there's no `campaign.toml`, don't guess. Copy `${CLAUDE_SKILL_DIR}/campaign.example.toml` into the folder, then ask the marketer, in one short message, for the values you can't find in the assets:

1. The campaign name used in `utm_campaign`.
2. Their own website domains. Links to these must carry UTM tags.
3. The allowed UTM mediums and sources, and which folder is which channel.
4. The approved offer: promo code, discount, end date, prices. These become `[[facts]]`.
5. The landing page file, its analytics snippet, and the form fields it must have.
6. The brand voice and exactly what's on offer, for the `[brand]` section.

Fill in only what they confirm. `${CLAUDE_SKILL_DIR}/reference/checks.md` explains every setting and check if they ask.

## 2. Run the script

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/campaign_qa.py <campaign-folder> --format json
```

Add `--online` only if the marketer wants links opened, and only for live sites, because it sends a request to every link. Without it, say plainly that links weren't opened.

Exit code 1 means the script found errors, which is normal. Exit code 2 means the script couldn't run: the folder or `campaign.toml` is broken, or Python is older than 3.11. Pass on the message in plain words, including how to fix it, and stop.

## 3. Review what the script can't judge

Read `[brand]` in `campaign.toml`, then read every asset in full. Look for:

- **Offer drift:** an asset promises a different discount, scope, or perk than `[brand].offer_scope`. For example, "all bikes" when only e-bikes are on sale, or free shipping nobody approved.
- **Link intent:** a call to action that goes somewhere other than where it says, like "Shop the sale" linking to the homepage.
- **Unsupported claims:** superlatives, statistics, guarantees, and urgency the marketer can't back up. The script flags some words as `review`; decide for each one whether it's a real problem or fine, and catch the ones it misses, like "our biggest sale of the year".
- **Voice and accessibility:** breaks from `[brand].voice`, all caps, jargon for the wrong audience, links and images that make no sense to a screen reader.
- **Consistency across channels:** the emails, social posts and landing page should describe the same offer the same way.

For each issue, quote the exact words, give the file and line, and say why it matters to a customer or to the campaign's results. Don't repeat a script error or warning as a judgment call.

## 4. Write the report

```markdown
# Campaign QA: <campaign name>

**Verdict:** Ready to launch / Fix <N> things before launch / Not ready

## Must fix before launch
<script errors, grouped by asset, each with the fix in one line>

## Should fix
<script warnings>

## Judgment calls
<your findings, each with the quote, file:line, and why it matters>

## Not checked
<what this run didn't cover: links not opened, images not viewed, emails not rendered in mail clients>
```

Keep it short. A marketer should be able to work down the list without asking you what anything means.

## Rules

- Never edit the marketer's assets unless they ask. If they do, change only what a finding covers, then run the script again.
- Never say a link works unless the run used `--online` and the link passed.
- Never invent approved values. If a fact is missing from `campaign.toml`, ask.
- If something looks deliberate, like a separate code for a partner channel, ask instead of calling it an error.

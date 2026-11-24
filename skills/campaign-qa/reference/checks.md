# Campaign QA checks

Each finding has a check name, a severity and a location. **Errors** should block the launch. **Warnings** are worth fixing. **Review** items go to a person or the AI review, because a script can't tell whether they're fine.

## Settings that drive the checks

| Setting | What it does |
|---|---|
| `[campaign] name` | The value every `utm_campaign` must match. |
| `[campaign] name_pattern` | A regular expression the campaign name itself must follow. |
| `[brand] voice`, `offer_scope` | Used only by the AI review, to judge tone and offer drift. |
| `[utm] required` | UTM parameters every link to your own sites must carry. |
| `[utm] allowed_mediums`, `allowed_sources` | The only values allowed for `utm_medium` and `utm_source`. |
| `[utm] lowercase` | UTM values must be lowercase, so reports don't split "Email" from "email". |
| `[utm] tracked_domains` | Your own domains. Only links to these are checked for UTM tags. Subdomains count. |
| `[utm.channels]` | Maps a folder name to the `utm_medium` its links must use. |
| `[links] blocked_hosts` | Hosts that must never appear in a live campaign, like staging or localhost. |
| `[links] require_https` | Warns on `http://` links. |
| `[[facts]]` | Approved values. Every match of `pattern` must equal `expected`. If the pattern has a group, only the group is compared. |
| `[landing]` | The landing page file, its analytics snippet, required form fields, and whether the form must capture UTM values. |
| `[claims]` | Words and numbers that send a line to the review list. |

## Checks

| Check | Severity | What it means | Usual fix |
|---|---|---|---|
| `naming` | error | The campaign name doesn't follow `name_pattern`. | Rename the campaign before any links go out. |
| `malformed-url` | error | The link has a space, a doubled `??` or `&&`, or a second `?`. | Rebuild the link from your UTM builder. |
| `blocked-host` | error | The link points to staging, localhost, or another blocked host. | Swap in the live URL. |
| `insecure-link` | warning | The link uses `http://`. | Change it to `https://`. |
| `utm-missing` | error | A link to your own site is missing a required UTM parameter. | Add the parameter. |
| `utm-case` | error | A UTM value has capital letters. | Make it lowercase. |
| `utm-format` | error | A UTM value has a space. | Use hyphens instead. |
| `utm-campaign` | error | `utm_campaign` isn't the campaign name. | Use the exact name from `campaign.toml`. |
| `utm-medium` | error | `utm_medium` isn't an allowed value. | Pick one from `allowed_mediums`. |
| `utm-channel` | error | The medium doesn't match the asset's folder, for example a social medium in an email. | Use the medium for that channel. |
| `utm-source` | warning | `utm_source` isn't in the allowed list. | Pick an allowed source, or add it to the list if it's new. |
| `fact-mismatch` | error | A promo code, discount, date or other fact doesn't match the approved value. | Correct the copy, or the approved value if the copy is right. |
| `landing-missing` | error | The landing page file isn't in the folder. | Add it, or fix `[landing] file`. |
| `tracking` | error | The landing page has no analytics snippet. | Add your tag. |
| `form` | error | The landing page has no form, or the form lacks a required field. | Add the form or field. |
| `utm-capture` | error | The form doesn't pass a UTM value to your CRM in a hidden field. | Add a hidden field for each required UTM parameter. |
| `page-meta` | warning | The landing page has no title or meta description. | Add them; they show in search results and link previews. |
| `alt-text` | warning | An image has no `alt` attribute. | Describe the image, or use `alt=""` if it's decoration. |
| `claim` | review | A line uses a flagged word or an unapproved number. | Confirm a source or approval, or reword. |
| `dead-link` | error | With `--online`: the link failed to load. | Fix or replace the link. |
| `redirect` | warning | With `--online`: the link redirects. | Link to the final address so UTM tags aren't lost. |

## Writing fact patterns

A fact check only sees text that matches its pattern. If a typo also breaks the pattern, like `FAL10` against `\b[A-Z]{4,}\d{2}\b`, the script won't see it, so keep patterns loose: `\b[A-Z]{3,}\d{1,3}\b` catches more near-misses than an exact match would. The AI review reads every asset and is the second net.

## What the script doesn't check

It doesn't open links unless you pass `--online`, look at images, render emails in mail clients, or judge tone, offer scope and claims. The AI review in `SKILL.md` covers the reading part; a person should still send a test email to themselves.

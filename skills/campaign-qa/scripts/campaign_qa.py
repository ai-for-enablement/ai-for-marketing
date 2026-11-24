#!/usr/bin/env python3
"""Campaign QA: deterministic pre-launch checks for a marketing campaign folder.

Reads campaign.toml (rules and approved facts) plus every .html, .htm, .md and .txt asset in the
folder, then checks links, UTM tags, approved facts, landing-page tracking and forms, image alt
text, and phrases that need a human or AI judgment. Standard library only (Python 3.11+).

Usage:
  campaign_qa.py CAMPAIGN_DIR [--format md|json] [--out FILE] [--online]

Exit code: 0 = no errors, 1 = at least one error, 2 = bad input.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # older Pythons, such as the one macOS ships
    try:
        import tomli as tomllib  # pyright: ignore[reportMissingImports]
    except ModuleNotFoundError:
        print(f"campaign-qa needs Python 3.11 or newer (this is {sys.version.split()[0]}). "
              "Install it from python.org or with `brew install python`, then run python3 again.", file=sys.stderr)
        sys.exit(2)
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

ASSET_SUFFIXES = {".html", ".htm", ".md", ".txt"}
STATIC_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".css", ".js", ".pdf", ".ico")
SEVERITY_ORDER = {"error": 0, "warning": 1, "review": 2}
URL_RE = re.compile(r"""https?://[^\s<>"'()\[\]]+""", re.I)
MD_LINK_RE = re.compile(r"\]\((\S+?)\)")
NUM_RX = re.compile(r"\b\d+(\.\d+)?\s?(%|x\b|times\b)", re.I)


class ConfigError(ValueError):
    """campaign.toml is missing a required setting or has one of the wrong type."""


@dataclass
class Finding:
    check: str
    severity: str  # error | warning | review
    asset: str
    line: int | None
    detail: str
    evidence: str = ""


@dataclass
class Link:
    url: str
    asset: str
    line: int


@dataclass
class Report:
    campaign: str
    assets: list[str] = field(default_factory=list)
    links_checked: int = 0
    findings: list[Finding] = field(default_factory=list)

    def add(self, *args, **kwargs) -> None:
        self.findings.append(Finding(*args, **kwargs))

    def counts(self) -> dict[str, int]:
        c = {"error": 0, "warning": 0, "review": 0}
        for f in self.findings:
            c[f.severity] += 1
        return c


# ---------------------------------------------------------------- reading assets

class _HTMLScan(HTMLParser):
    """Collects links, images, forms and inputs with line numbers."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, int]] = []
        self.images: list[tuple[dict, int]] = []
        self.forms: list[dict] = []
        self.inputs: list[dict] = []  # each has "_form": index into self.forms, or None if outside every form
        self.metas: list[dict] = []
        self._open_form: int | None = None

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        line = self.getpos()[0]
        if tag == "a" and a.get("href"):
            self.links.append((a["href"], line))
        elif tag == "form":
            self.forms.append(a)
            self._open_form = len(self.forms) - 1
            if a.get("action"):
                self.links.append((a["action"], line))
        elif tag == "img":
            self.images.append((a, line))
        elif tag == "meta":
            self.metas.append(a)
        elif tag in ("input", "select", "textarea"):
            self.inputs.append({**a, "_form": self._open_form, "_tag": tag})

    def handle_endtag(self, tag):
        if tag == "form":
            self._open_form = None

    def form_fields(self) -> list[dict]:
        """Inputs that a form submits: inside a <form>, or pointing at one with form="id"."""
        ids = {f.get("id") for f in self.forms if f.get("id")}
        return [i for i in self.inputs
                if "disabled" not in i and (i["_form"] is not None or i.get("form") in ids)]


def load_assets(root: Path) -> dict[str, str]:
    assets = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in ASSET_SUFFIXES and not p.name.startswith("."):
            assets[p.relative_to(root).as_posix()] = p.read_text(encoding="utf-8")
    return assets


def extract_links(name: str, text: str) -> list[Link]:
    links: list[Link] = []
    seen: set[tuple[str, int]] = set()
    if name.endswith((".html", ".htm")):
        scan = _HTMLScan()
        scan.feed(text)
        for url, line in scan.links:
            if is_web_url(url):
                links.append(Link(url, name, line))
                seen.add((url, line))
        return links  # HTML: only real hrefs and form actions, never image or script URLs
    for i, line_text in enumerate(text.splitlines(), start=1):
        found = [m.group(1) for m in MD_LINK_RE.finditer(line_text)] + URL_RE.findall(line_text)
        for url in found:
            url = url.rstrip(".,;:!?")
            if is_web_url(url) and (url, i) not in seen:
                links.append(Link(url, name, i))
                seen.add((url, i))
    return links


def is_web_url(url: str) -> bool:
    """http(s) links in any letter case, plus network-relative ones (//host/path)."""
    return url.lower().startswith(("http://", "https://")) or (url.startswith("//") and len(url) > 2 and url[2] != "/")


def absolute(url: str) -> str:
    """A network-relative link loads over the page's scheme; campaign pages are https."""
    return "https:" + url if url.startswith("//") else url


def line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def visible_text(name: str, text: str) -> str:
    """The words a customer sees: HTML tags stripped (keeping line breaks) and entities decoded,
    so &#48; reads as 0 and &nbsp; as a space."""
    if not name.endswith((".html", ".htm")):
        return text
    no_blocks = re.sub(r"<(script|style)\b.*?</\1>", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S | re.I)
    stripped = re.sub(r"<[^>]+>", lambda m: "\n" * m.group(0).count("\n") or " ", no_blocks)
    return html.unescape(stripped).replace("\xa0", " ")


# ---------------------------------------------------------------- checks

def check_campaign_name(cfg: dict, rep: Report) -> None:
    c = cfg.get("campaign", {})
    name, pattern = c.get("name", ""), c.get("name_pattern")
    if pattern and not re.fullmatch(pattern, name):
        rep.add("naming", "error", "campaign.toml", None,
                f"Campaign name '{name}' doesn't match the naming convention {pattern}.")


def channel_for(asset: str, cfg: dict) -> str | None:
    """Expected utm_medium for an asset, from the folder it sits in ([utm.channels])."""
    channels = cfg.get("utm", {}).get("channels", {})
    first = asset.split("/", 1)[0] if "/" in asset else ""
    return channels.get(first)


def check_link(link: Link, cfg: dict, rep: Report) -> None:
    lc, uc = cfg.get("links", {}), cfg.get("utm", {})
    camp = cfg.get("campaign", {}).get("name", "")
    ev = link.url
    url = absolute(link.url)
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        parts.port  # noqa: B018 -- raises ValueError on a bad port
    except ValueError as e:
        rep.add("malformed-url", "error", link.asset, link.line, f"URL can't be parsed ({e}).", ev)
        return
    if not host:
        rep.add("malformed-url", "error", link.asset, link.line, "URL has no host name.", ev)
        return

    if "??" in url or "&&" in url or url.count("?") > 1:
        rep.add("malformed-url", "error", link.asset, link.line, "Malformed query string.", ev)
    if " " in url or "%20" in url:
        rep.add("malformed-url", "error", link.asset, link.line, "URL contains a space.", ev)
    if host in [h.lower() for h in lc.get("blocked_hosts", [])]:
        rep.add("blocked-host", "error", link.asset, link.line,
                f"Links to {host}, which must never ship (staging, local, or internal).", ev)
    if lc.get("require_https", True) and parts.scheme == "http":
        rep.add("insecure-link", "warning", link.asset, link.line, "Uses http:// instead of https://.", ev)

    tracked = any(host == d or host.endswith("." + d) for d in uc.get("tracked_domains", []))
    if not tracked or parts.path.lower().endswith(STATIC_SUFFIXES):
        return
    params = dict(parse_qsl(parts.query.replace("??", "?").lstrip("?"), keep_blank_values=True))
    utm = {k: v for k, v in params.items() if k.startswith("utm_")}
    missing = [k for k in uc.get("required", []) if not utm.get(k)]
    if missing:
        rep.add("utm-missing", "error", link.asset, link.line, f"Missing {', '.join(missing)}.", ev)
    for k, v in utm.items():
        if uc.get("lowercase", True) and v != v.lower():
            rep.add("utm-case", "error", link.asset, link.line, f"{k}='{v}' isn't lowercase.", ev)
        if " " in v:
            rep.add("utm-format", "error", link.asset, link.line, f"{k}='{v}' contains a space.", ev)
    if utm.get("utm_campaign") and utm["utm_campaign"].lower() != camp.lower():
        rep.add("utm-campaign", "error", link.asset, link.line,
                f"utm_campaign='{utm['utm_campaign']}' doesn't match the campaign name '{camp}'.", ev)
    med = utm.get("utm_medium")
    if med and uc.get("allowed_mediums") and med not in uc["allowed_mediums"]:
        rep.add("utm-medium", "error", link.asset, link.line,
                f"utm_medium='{med}' isn't one of {uc['allowed_mediums']}.", ev)
    expected = channel_for(link.asset, cfg)
    if med and expected and med != expected:
        rep.add("utm-channel", "error", link.asset, link.line,
                f"utm_medium='{med}' in an asset under {link.asset.split('/')[0]}/; expected '{expected}'.", ev)
    src = utm.get("utm_source")
    if src and uc.get("allowed_sources") and src not in uc["allowed_sources"]:
        rep.add("utm-source", "warning", link.asset, link.line,
                f"utm_source='{src}' isn't one of {uc['allowed_sources']}.", ev)


def check_facts(assets: dict[str, str], cfg: dict, rep: Report) -> None:
    for fact in cfg.get("facts", []):
        rx = re.compile(fact["pattern"], 0 if fact.get("case_sensitive", True) else re.I)
        want = fact["expected"]
        norm = (lambda s: " ".join(s.split())) if fact.get("case_sensitive", True) else (lambda s: " ".join(s.split()).lower())
        for name, text in assets.items():
            body = visible_text(name, text)
            for m in rx.finditer(body):
                got = m.group(1) if rx.groups else m.group(0)  # with a capture group, compare only the group
                if norm(got) != norm(want):
                    rep.add("fact-mismatch", "error", name, line_of(body, m.start()),
                            f"{fact['name']}: found '{got}', approved value is '{want}'.", m.group(0))


def check_landing(assets: dict[str, str], cfg: dict, rep: Report) -> None:
    lc = cfg.get("landing")
    if not lc:
        return
    name = lc.get("file", "")
    if name not in assets:
        rep.add("landing-missing", "error", name or "campaign.toml", None, "Landing page file not found.")
        return
    text = assets[name]
    for pat in lc.get("tracking_patterns", []):
        if not re.search(pat, text):
            rep.add("tracking", "error", name, None, f"No analytics snippet matching '{pat}'.")
    scan = _HTMLScan()
    scan.feed(text)
    if lc.get("required_form_fields") and not scan.forms:
        rep.add("form", "error", name, None, "No form on the landing page.")
    fields = scan.form_fields()
    field_names = {i.get("name", "") for i in fields}
    for f in lc.get("required_form_fields", []):
        if f not in field_names:
            rep.add("form", "error", name, None, f"Form has no '{f}' field (fields outside the form or disabled don't count).")
    if lc.get("hidden_utm_fields"):
        hidden = {i.get("name", "") for i in fields if i["_tag"] == "input" and i.get("type", "").lower() == "hidden"}
        for k in cfg.get("utm", {}).get("required", []):
            if k not in hidden:
                rep.add("utm-capture", "error", name, None,
                        f"Form doesn't capture {k} in a hidden field, so the CRM won't know where leads came from.")
    if not re.search(r"<title>\s*\S", text, re.I):
        rep.add("page-meta", "warning", name, None, "Page has no <title>.")
    if not any(m.get("name", "").lower() == "description" and m.get("content", "").strip() for m in scan.metas):
        rep.add("page-meta", "warning", name, None, "Page has no meta description.")


def check_images(assets: dict[str, str], rep: Report) -> None:
    for name, text in assets.items():
        if not name.endswith((".html", ".htm")):
            continue
        scan = _HTMLScan()
        scan.feed(text)
        for a, line in scan.images:
            if "alt" not in a:
                rep.add("alt-text", "warning", name, line, "Image has no alt text.", a.get("src", ""))


def flag_claims(assets: dict[str, str], cfg: dict, rep: Report) -> None:
    cc = cfg.get("claims", {})
    words = cc.get("flag_words", [])
    if not words and not cc.get("flag_numbers", True):
        return
    word_rx = re.compile(r"(?<![\w#])(" + "|".join(re.escape(w) for w in words) + r")(?!\w)", re.I) if words else None
    def token(s: str) -> str:
        return "".join(s.split()).lower()
    approved = {token(m.group(0)) for f in cfg.get("facts", []) for m in NUM_RX.finditer(f["expected"])}
    for name, text in assets.items():
        for i, line_text in enumerate(visible_text(name, text).splitlines(), start=1):
            if URL_RE.search(line_text) and not URL_RE.sub("", line_text).strip(" -*[]()"):
                continue
            hits = []
            if word_rx:
                hits += [m.group(0) for m in word_rx.finditer(line_text)]
            if cc.get("flag_numbers", True):
                hits += [m.group(0) for m in NUM_RX.finditer(line_text) if token(m.group(0)) not in approved]
            if hits:
                rep.add("claim", "review", name, i,
                        f"Needs a source or approval: {', '.join(dict.fromkeys(hits))}.", line_text.strip()[:200])


def check_online(links: list[Link], rep: Report, timeout: float = 8.0) -> None:
    for url in dict.fromkeys(l.url for l in links):
        where = next(l for l in links if l.url == url)
        target = absolute(url)
        try:
            try:
                final = _open(target, "HEAD", timeout)
            except urllib.error.HTTPError as e:
                if e.code not in (403, 405, 501):  # some servers refuse HEAD but serve GET
                    raise
                final = _open(target, "GET", timeout)
            if final != target:
                rep.add("redirect", "warning", where.asset, where.line, f"Redirects to {final}.", url)
        except urllib.error.HTTPError as e:
            rep.add("dead-link", "error", where.asset, where.line, f"HTTP {e.code}.", url)
        except ValueError as e:
            rep.add("malformed-url", "error", where.asset, where.line, f"URL can't be opened ({e}).", url)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            rep.add("dead-link", "error", where.asset, where.line, f"Couldn't connect ({getattr(e, 'reason', e)}).", url)


def _open(url: str, method: str, timeout: float) -> str:
    """Opens url and returns the final address after redirects. GET reads at most 1 byte."""
    headers = {"User-Agent": "campaign-qa"} | ({"Range": "bytes=0-0"} if method == "GET" else {})
    with urllib.request.urlopen(urllib.request.Request(url, method=method, headers=headers), timeout=timeout) as r:
        if method == "GET":
            r.read(1)
        return r.geturl()


# ---------------------------------------------------------------- settings

def _require(ok: bool, msg: str) -> None:
    if not ok:
        raise ConfigError(f"campaign.toml: {msg}")


def _is_str_list(v) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


def _compiles(pattern: str, where: str) -> None:
    try:
        re.compile(pattern)
    except re.error as e:
        raise ConfigError(f"campaign.toml: {where} isn't a valid regular expression ({e}).") from None


def validate_config(cfg: dict) -> None:
    """Fails fast on settings that would make checks silently pass. See reference/checks.md."""
    c = cfg.get("campaign")
    _require(isinstance(c, dict) and isinstance(c.get("name"), str) and c["name"].strip(),
             "[campaign] needs a name (every utm_campaign must equal it).")
    if "name_pattern" in c:
        _require(isinstance(c["name_pattern"], str), "[campaign] name_pattern must be text.")
        _compiles(c["name_pattern"], "[campaign] name_pattern")
    u = cfg.get("utm")
    _require(isinstance(u, dict) and _is_str_list(u.get("tracked_domains")) and u["tracked_domains"],
             "[utm] needs tracked_domains, the sites whose links must carry UTM tags.")
    for k in ("required", "allowed_mediums", "allowed_sources"):
        _require(k not in u or _is_str_list(u[k]), f"[utm] {k} must be a list of text values.")
    _require(isinstance(u.get("channels", {}), dict), "[utm.channels] must map folder names to mediums.")
    lk = cfg.get("links", {})
    _require(isinstance(lk, dict) and _is_str_list(lk.get("blocked_hosts", [])), "[links] blocked_hosts must be a list of host names.")
    facts = cfg.get("facts", [])
    _require(isinstance(facts, list), "[[facts]] must be a list of tables.")
    for i, f in enumerate(facts, start=1):
        _require(isinstance(f, dict) and all(isinstance(f.get(k), str) for k in ("name", "pattern", "expected")),
                 f"fact {i} needs name, pattern and expected, all as text.")
        _compiles(f["pattern"], f"the pattern for fact '{f['name']}'")
    land = cfg.get("landing")
    if land is not None:
        _require(isinstance(land, dict) and isinstance(land.get("file"), str) and land["file"],
                 "[landing] needs file, the landing page's path inside the campaign folder.")
        _require(_is_str_list(land.get("tracking_patterns", [])), "[landing] tracking_patterns must be a list of text values.")
        for pat in land.get("tracking_patterns", []):
            _compiles(pat, f"[landing] tracking pattern '{pat}'")
        _require(_is_str_list(land.get("required_form_fields", [])), "[landing] required_form_fields must be a list of field names.")
    cl = cfg.get("claims", {})
    _require(isinstance(cl, dict) and _is_str_list(cl.get("flag_words", [])), "[claims] flag_words must be a list of text values.")


# ---------------------------------------------------------------- run + output

def run(root: Path, online: bool = False) -> Report:
    cfg_path = root / "campaign.toml"
    if not cfg_path.exists():
        raise FileNotFoundError(f"{cfg_path} not found")
    cfg = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    validate_config(cfg)
    rep = Report(campaign=cfg["campaign"]["name"])
    assets = load_assets(root)
    rep.assets = list(assets)
    check_campaign_name(cfg, rep)
    links = [l for name, text in assets.items() for l in extract_links(name, text)]
    rep.links_checked = len(links)
    for l in links:
        check_link(l, cfg, rep)
    check_facts(assets, cfg, rep)
    check_landing(assets, cfg, rep)
    check_images(assets, rep)
    flag_claims(assets, cfg, rep)
    if online:
        check_online(links, rep)
    rep.findings.sort(key=lambda f: (SEVERITY_ORDER[f.severity], f.asset, f.line or 0))
    return rep


def to_markdown(rep: Report, online: bool) -> str:
    c = rep.counts()
    out = [f"# Campaign QA: {rep.campaign}", "",
           f"{len(rep.assets)} assets, {rep.links_checked} links. "
           f"**{c['error']} errors**, {c['warning']} warnings, {c['review']} items for review.",
           "" if online else "Links were not opened (offline run); pass --online to check that they load.", ""]
    titles = {"error": "Errors (fix before launch)", "warning": "Warnings", "review": "Needs review (judgment calls)"}
    for sev in ("error", "warning", "review"):
        items = [f for f in rep.findings if f.severity == sev]
        if not items:
            continue
        out += [f"## {titles[sev]}", ""]
        for f in items:
            loc = f"{f.asset}:{f.line}" if f.line else f.asset
            out.append(f"- **{f.check}** `{loc}`: {f.detail}" + (f"  \n  `{f.evidence}`" if f.evidence else ""))
        out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("campaign_dir", type=Path)
    ap.add_argument("--format", choices=["md", "json"], default="md")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--online", action="store_true", help="also open each link and report dead links and redirects")
    a = ap.parse_args(argv)
    try:
        rep = run(a.campaign_dir, online=a.online)
    except (FileNotFoundError, tomllib.TOMLDecodeError, ConfigError) as e:
        print(f"campaign-qa: {e}", file=sys.stderr)
        return 2
    text = (json.dumps({**asdict(rep), "counts": rep.counts()}, indent=2) if a.format == "json"
            else to_markdown(rep, a.online))
    if a.out:
        a.out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 1 if rep.counts()["error"] else 0


if __name__ == "__main__":
    sys.exit(main())

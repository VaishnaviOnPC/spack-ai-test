import json
import os
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List, Optional


_CACHE_TTL = 86400
_ATOM_NS = "{http://www.w3.org/2005/Atom}"

_BUILD_KEYWORDS = {
    "build", "install", "compile", "compilation", "cmake", "configure",
    "linker", "link", "compiler", "gcc", "clang", "icc", "nvhpc", "intel",
    "oneapi", "fortran", "makefile", "meson", "autotools", "error", "fail",
    "broken", "regression", "crash", "segfault",
}


@dataclass
class GithubSignal:
    open_issues: int
    open_prs: int
    slug: str


def _cache_path() -> str:
    base = os.path.expanduser("~/.spack/ai_test")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "github_cache.json")


def _load_cache() -> dict:
    path = _cache_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


def _save_cache(cache: dict) -> None:
    with open(_cache_path(), "w") as f:
        json.dump(cache, f)


def _fetch(url: str, accept: str = "text/html") -> Optional[str]:
    headers = {"User-Agent": "spack-ai-test-scraper", "Accept": accept}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError:
        return None


def _parse_github_slug(url: str) -> Optional[str]:
    if not url:
        return None
    m = re.search(r"github\.com[/:]([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", url)
    if not m:
        return None
    slug = m.group(1).rstrip("/")
    return re.sub(r"\.git$", "", slug)


def _parse_count(html: str, element_id: str) -> int:
    m = re.search(rf'id="{element_id}"[^>]*>([^<]+)<', html)
    if not m:
        return 0
    text = m.group(1).strip().lower().replace(",", "")
    if text.endswith("k"):
        try:
            return int(float(text[:-1]) * 1000)
        except ValueError:
            return 0
    try:
        return int(text)
    except ValueError:
        return 0


def _parse_atom(xml_text: str) -> List[dict]:
    entries = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return entries

    for entry in root.findall(f"{_ATOM_NS}entry"):
        title_el = entry.find(f"{_ATOM_NS}title")
        content_el = entry.find(f"{_ATOM_NS}content")
        link_el = entry.find(f"{_ATOM_NS}link")

        title = (title_el.text or "").strip()
        body_html = content_el.text or "" if content_el is not None else ""
        url = link_el.get("href", "") if link_el is not None else ""

        body_text = re.sub(r"<[^>]+>", " ", body_html)
        body_text = re.sub(r"\s+", " ", body_text).strip()

        num_m = re.search(r"/issues/(\d+)", url)
        entries.append({
            "num": num_m.group(1) if num_m else "?",
            "title": title,
            "body": body_text,
            "url": url,
        })

    return entries


def _score_entry(entry: dict, compiler_names: List[str]) -> int:
    """Score an issue by relevance. Higher = more relevant."""
    text = (entry["title"] + " " + entry["body"]).lower()
    score = 0
    score += sum(1 for kw in _BUILD_KEYWORDS if kw in text)
    score += sum(3 for cn in compiler_names if cn in text)
    return score


def fetch_github_signal(pkg_name: str) -> Optional[GithubSignal]:
    try:
        import spack.repo
        pkg_cls = spack.repo.PATH.get_pkg_class(pkg_name)
        homepage = getattr(pkg_cls, "homepage", "") or ""
        git_url = getattr(pkg_cls, "git", "") or ""
    except spack.repo.UnknownPackageError:
        return None

    slug = _parse_github_slug(homepage) or _parse_github_slug(git_url)
    if not slug:
        return None

    cache = _load_cache()
    entry = cache.get(slug)
    if entry and (time.time() - entry.get("ts", 0)) < _CACHE_TTL:
        return GithubSignal(
            open_issues=entry["open_issues"],
            open_prs=entry["open_prs"],
            slug=slug,
        )

    html = _fetch(f"https://github.com/{slug}")
    if not html:
        return None

    open_issues = _parse_count(html, "issues-repo-tab-count")
    open_prs = _parse_count(html, "pull-requests-repo-tab-count")

    cache[slug] = {"open_issues": open_issues, "open_prs": open_prs, "ts": time.time()}
    _save_cache(cache)

    return GithubSignal(open_issues=open_issues, open_prs=open_prs, slug=slug)


def fetch_issue_context(
    slug: str,
    compilers: Optional[List[str]] = None,
    limit: int = 20,
) -> str:
    compiler_names = []
    if compilers:
        for c in compilers:
            compiler_names.append(c.split("@")[0].lower())

    cache_key = f"{slug}::issues::{','.join(sorted(compiler_names))}::{limit}"
    cache = _load_cache()
    cached = cache.get(cache_key)
    if cached and (time.time() - cached.get("ts", 0)) < _CACHE_TTL:
        return cached.get("context", "")

    xml_text = _fetch(
        f"https://github.com/{slug}/issues.atom",
        accept="application/atom+xml",
    )
    if not xml_text:
        return ""

    entries = _parse_atom(xml_text)
    if not entries:
        return ""

    scored = sorted(entries, key=lambda e: _score_entry(e, compiler_names), reverse=True)

    relevant = [e for e in scored if _score_entry(e, compiler_names) > 0]
    if len(relevant) < 3:
        relevant = scored

    selected = relevant[:limit]
    if not selected:
        return ""

    lines = [f"Recent relevant build/install issues from {slug} (GitHub):"]
    for e in selected:
        lines.append(f"  #{e['num']}: {e['title']}")
        if e["body"]:
            snippet = e["body"][:200]
            if len(e["body"]) > 200:
                snippet = snippet.rsplit(" ", 1)[0] + "..."
            lines.append(f"    => {snippet}")

    context = "\n".join(lines)

    cache[cache_key] = {"context": context, "ts": time.time()}
    _save_cache(cache)

    return context

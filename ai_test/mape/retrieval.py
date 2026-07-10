import glob
import math
import os
import pickle
import re

import spack.paths
import spack.repo

_DEP_RE = re.compile(r"""depends_on\s*\(\s*["']([^"'@\s,]+)""")
_CLASS_RE = re.compile(r'class\s+\w+\((\w+)\)')
_CACHE_FILE = os.path.join(spack.paths.user_cache_path, "ai_test", "pkg_index.pkl")

# tokens that appear in nearly every package and add no signal
_STOP = {
    "dep", "var", "buildsys", "build", "link", "run", "name",
    "true", "false", "package", "unknown", "none", "when", "type",
}


def _scan_packages() -> dict:
    pkgs = {}
    for repo in spack.repo.PATH.repos:
        pkg_dir = getattr(repo, "packages_path", None)
        if not pkg_dir or not os.path.isdir(pkg_dir):
            continue
        for path in glob.glob(os.path.join(pkg_dir, "**", "package.py"), recursive=True):
            name = os.path.basename(os.path.dirname(path))
            try:
                src = open(path, encoding="utf-8", errors="ignore").read()
                deps = list(set(_DEP_RE.findall(src)))
                m = _CLASS_RE.search(src)
                bsys = m.group(1).lower().replace("package", "") if m else "generic"
                pkgs[name] = {"deps": deps, "build_sys": bsys, "path": path}
            except Exception:
                continue
    return pkgs


def _pkg_card(name: str, info: dict) -> str:
    deps_str = " ".join(f"dep:{d}" for d in sorted(info["deps"]))
    return f"name:{name} buildsys:{info['build_sys']} {deps_str}"


def _schema_card(schema) -> str:
    by_type = {}
    for dep in schema.dependencies:
        for t in (dep.dep_type or ["build"]):
            by_type.setdefault(t.lower(), []).append(dep.name)

    deps_str = " ".join(
        f"dep_{t}:" + ",".join(sorted(set(names)))
        for t, names in sorted(by_type.items())
    )
    bs_var = schema.variants.get("build_system")
    bs = f"buildsys:{bs_var.default}" if bs_var else "buildsys:generic"
    return f"name:{schema.name} {bs} {deps_str}"


def _tokenize(card: str) -> list:
    tokens = re.findall(r'[a-z0-9_\-]+', card.lower())
    return [t for t in tokens if t not in _STOP and len(t) > 1]


def _idf(token_lists: list) -> dict:
    N = len(token_lists)
    df = {}
    for toks in token_lists:
        for t in set(toks):
            df[t] = df.get(t, 0) + 1
    return {t: math.log(N / cnt) for t, cnt in df.items()}


def _cosine(qtoks: list, dtoks: list, weights: dict) -> float:
    qtf = {}
    for t in qtoks:
        qtf[t] = qtf.get(t, 0) + 1
    dtf = {}
    for t in dtoks:
        dtf[t] = dtf.get(t, 0) + 1

    qn = len(qtoks) or 1
    dn = len(dtoks) or 1

    dot = sum(
        (qtf[t] / qn) * weights.get(t, 0) * (dtf[t] / dn) * weights.get(t, 0)
        for t in qtf if t in dtf
    )
    qmag = math.sqrt(sum(((c / qn) * weights.get(t, 0)) ** 2 for t, c in qtf.items()))
    dmag = math.sqrt(sum(((c / dn) * weights.get(t, 0)) ** 2 for t, c in dtf.items()))
    return dot / (qmag * dmag) if qmag and dmag else 0.0


_index = None


def _load_index() -> dict:
    global _index
    if _index is not None:
        return _index

    if os.path.exists(_CACHE_FILE):
        with open(_CACHE_FILE, "rb") as f:
            _index = pickle.load(f)
        return _index

    print("Building package index (first run, takes ~10s)...")
    pkgs = _scan_packages()
    tok_index = {name: _tokenize(_pkg_card(name, info)) for name, info in pkgs.items()}
    weights = _idf(list(tok_index.values()))

    _index = {"pkgs": pkgs, "tokens": tok_index, "idf": weights}
    os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
    with open(_CACHE_FILE, "wb") as f:
        pickle.dump(_index, f)
    return _index


def find_similar(schema, top_n=2) -> list:
    idx = _load_index()
    weights = idx["idf"]
    tok_index = idx["tokens"]

    qtoks = _tokenize(_schema_card(schema))
    scores = {
        name: _cosine(qtoks, toks, weights)
        for name, toks in tok_index.items()
        if name != schema.name
    }
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_n]


def get_chunks(pkg_name: str) -> str:
    idx = _load_index()
    info = idx["pkgs"].get(pkg_name)
    if not info:
        return ""
    src = open(info["path"], encoding="utf-8", errors="ignore").read()
    chunks = []
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith(("depends_on(", "variant(", "conflicts(")):
            chunks.append("  " + stripped)
        if len(chunks) >= 15:
            break
    return "\n".join(chunks)

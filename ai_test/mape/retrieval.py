import re
import spack.repo
from ai_test.extract.schema import PackageSchema


def _versions_for(dep_name: str) -> list:
    try:
        pkg_class = spack.repo.PATH.get_pkg_class(dep_name)
        raw = list(getattr(pkg_class, "versions", {}).keys())
        return sorted(raw, key=lambda v: [int(x) for x in str(v).split(".") if x.isdigit()])
    except Exception:
        return []


def _parse_min(bound: str) -> str:
    if not bound or bound in (":", ""):
        return None
    return bound.lstrip("@").split(":")[0] or None


def _major(version_str: str) -> int:
    parts = str(version_str).split(".")
    return int(parts[0]) if parts and parts[0].isdigit() else -1


def _is_open(bound: str) -> bool:
    if not bound or bound == ":":
        return True
    parts = bound.split(":")
    return len(parts) == 2 and parts[1] == ""


def _ge(v: str, minimum: str) -> bool:
    def parts(s):
        return [int(x) for x in s.split(".") if x.isdigit()]
    return parts(v) >= parts(minimum)


def compute_gaps(schema: PackageSchema) -> list:
    results = []
    seen = set()

    for dep in schema.dependencies:
        if dep.name in seen:
            continue
        seen.add(dep.name)

        if not _is_open(dep.bound):
            continue
        if spack.repo.PATH.is_virtual(dep.name):
            continue

        versions = _versions_for(dep.name)
        if not versions:
            continue

        min_str = _parse_min(dep.bound)
        latest_str = str(versions[-1])
        above = [v for v in versions if _ge(str(v), min_str)] if min_str else versions

        if not above:
            continue

        min_major = _major(min_str) if min_str else _major(str(above[0]))
        crossings = []
        seen_majors = set()
        for v in above:
            m = _major(str(v))
            if m > min_major and m not in seen_majors:
                seen_majors.add(m)
                crossings.append(str(v))

        results.append({
            "dep": dep.name,
            "min_declared": min_str or str(versions[0]),
            "latest": latest_str,
            "gap_count": len(above),
            "major_crossings": crossings,
        })

    return sorted(results, key=lambda x: (len(x["major_crossings"]), x["gap_count"]), reverse=True)


def gap_context(schema: PackageSchema) -> str:
    entries = [e for e in compute_gaps(schema) if e["major_crossings"]]
    if not entries:
        return ""

    lines = [
        f"Dependency version gaps for {schema.name} (open upper bounds only):",
    ]
    for e in entries[:5]:
        crossing_note = f" [major boundaries: {', '.join(e['major_crossings'])}]"
        lines.append(f"  {e['dep']}: @{e['min_declared']} to latest {e['latest']}{crossing_note}")
        lines.append(f"    floor pin: ^{e['dep']}@{e['min_declared']}")

    lines.append(
        "Use these floor pins in ^dep@version specs and also generate specs "
        "where these deps are left unpinned (they will resolve to their latest version)."
    )
    return "\n".join(lines)


def _parse_features(spec: str) -> set:
    features = set()
    for m in re.finditer(r'([+~])(\w+)', spec):
        features.add(f"{m.group(1)}{m.group(2)}")
    for m in re.finditer(r'(\w+)=(\w+)', spec):
        if m.group(1) not in ("arch", "os", "target"):
            features.add(f"{m.group(1)}={m.group(2)}")
    for m in re.finditer(r'\^([\w\-]+)@([\d\.]+)', spec):
        features.add(f"^{m.group(1)}@{m.group(2)}")
    return features


def kb_patterns(kb_entries: list) -> str:
    validated = [e for e in kb_entries if e.validation_status == "validated"]
    if len(validated) < 4:
        return ""

    failed = [e for e in validated if not e.concretized]
    passed = [e for e in validated if e.concretized]
    if not failed or not passed:
        return ""

    overall_fail_rate = len(failed) / len(validated)

    fail_counts = {}
    for e in failed:
        for feat in _parse_features(e.spec):
            fail_counts[feat] = fail_counts.get(feat, 0) + 1

    pass_counts = {}
    for e in passed:
        for feat in _parse_features(e.spec):
            pass_counts[feat] = pass_counts.get(feat, 0) + 1

    risky, safe = [], []
    all_features = set(fail_counts) | set(pass_counts)
    for feat in all_features:
        fc = fail_counts.get(feat, 0)
        pc = pass_counts.get(feat, 0)
        total = fc + pc
        if total < 2:
            continue
        feat_fail_rate = fc / total
        if feat_fail_rate > 0.85 and feat_fail_rate > overall_fail_rate:
            risky.append((feat, fc, total, feat_fail_rate))
        elif feat_fail_rate < 0.35 and pc >= 2:
            safe.append((feat, pc, total))

    if not risky and not safe:
        return ""

    lines = ["Empirical failure patterns from KB history:"]
    if risky:
        risky.sort(key=lambda x: x[3], reverse=True)
        lines.append("  High failure rate — prioritise testing these combinations:")
        for feat, fc, total, rate in risky[:5]:
            lines.append(f"    {feat}  ({fc}/{total} specs failed)")
    if safe:
        safe.sort(key=lambda x: x[1], reverse=True)
        lines.append("  Low failure rate — well-tested, de-prioritise:")
        for feat, pc, total in safe[:3]:
            lines.append(f"    {feat}  ({pc}/{total} specs passed)")
    return "\n".join(lines)

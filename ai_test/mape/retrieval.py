import re
import spack.repo
from ai_test.extract.schema import PackageSchema


def _versions_for(dep_name: str) -> list:
    try:
        pkg_class = spack.repo.PATH.get_pkg_class(dep_name)
        versions_dict = getattr(pkg_class, "versions", {})
        valid_versions = [v for v, args in versions_dict.items() if not args.get("deprecated", False)]
        return sorted(valid_versions, key=lambda v: [int(x) for x in str(v).split(".") if x.isdigit()])
    except spack.repo.UnknownPackageError:
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


def valid_dep_versions_context(schema: PackageSchema) -> str:
    from ai_test.config import BUILD_TOOLS

    target_deps = []
    seen = set()

    has_python_dep = any(dep.name == "python" for dep in schema.dependencies)
    if has_python_dep:
        target_deps.append("python")
        seen.add("python")

    for dep in schema.dependencies:
        if dep.name in seen or dep.name in BUILD_TOOLS:
            continue
        if spack.repo.PATH.is_virtual(dep.name):
            continue
        target_deps.append(dep.name)
        seen.add(dep.name)

    if not target_deps:
        return ""

    dep_lines = []
    for dep_name in target_deps[:10]:
        versions = _versions_for(dep_name)
        if not versions:
            continue
        shown = versions if len(versions) <= 10 else versions[:5] + versions[-3:]
        dep_lines.append(f"  {dep_name}: {', '.join(str(v) for v in shown)}")

    if not dep_lines:
        return ""

    return (
        "Valid Spack registry versions for key dependencies\n"
        "(ONLY pin ^dep@version using these exact strings, never guess a version;\n"
        " do NOT pin build tools such as py-pip, py-setuptools, py-wheel, cmake, ninja):\n"
        + "\n".join(dep_lines)
    )


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
        if feat_fail_rate > 0.85:
            risky.append((feat, fc, total, feat_fail_rate))
        elif feat_fail_rate < 0.35 and pc >= 2:
            safe.append((feat, pc, total))

    if not risky and not safe:
        return ""

    lines = ["Empirical failure patterns from KB history:"]
    if risky:
        risky.sort(key=lambda x: x[3], reverse=True)
        lines.append("  Never concretizes on this system - DO NOT generate specs with these:")
        for feat, fc, total, rate in risky[:5]:
            lines.append(f"    {feat}  ({fc}/{total} specs failed to concretize)")
    if safe:
        safe.sort(key=lambda x: x[1], reverse=True)
        lines.append("  Reliably concretizes - use these safe features as a stable base to build upon:")
        for feat, pc, total in safe[:3]:
            lines.append(f"    {feat}  ({pc}/{total} specs passed)")
    return "\n".join(lines)


def mine_persistent_patterns(all_kb_entries: list, threshold: float = 0.80, min_samples: int = 3) -> list:
    validated = [e for e in all_kb_entries if e.validation_status == "validated"]
    if len(validated) < min_samples:
        return []

    feat_fail = {}
    feat_total = {}
    build_fail = {}
    build_total = {}

    for e in validated:
        for feat in _parse_features(e.spec):
            feat_total[feat] = feat_total.get(feat, 0) + 1
            if not e.concretized:
                feat_fail[feat] = feat_fail.get(feat, 0) + 1
            if e.concretized:
                build_total[feat] = build_total.get(feat, 0) + 1
                if not e.installed and e.install_error:
                    build_fail[feat] = build_fail.get(feat, 0) + 1

    rules = []

    for feat, total in feat_total.items():
        if total < min_samples:
            continue
        fails = feat_fail.get(feat, 0)
        rate = fails / total
        if rate >= threshold:
            rules.append(
                f"Observed: '{feat}' fails concretization in {fails}/{total} tests "
                f"({rate*100:.0f}%) across all packages: DO NOT generate specs using this feature"
            )

    for feat, total in build_total.items():
        if total < min_samples:
            continue
        fails = build_fail.get(feat, 0)
        rate = fails / total
        if rate >= threshold:
            rules.append(
                f"Observed: '{feat}' causes build failures in {fails}/{total} "
                f"install attempts ({rate*100:.0f}%): highly valuable pattern! Use this to expose compilation bugs."
            )

    def _priority(r: str) -> int:
        if "^" in r:
            return 0
        if "%" in r:
            return 1
        return 2

    rules.sort(key=_priority)
    return rules[:10]


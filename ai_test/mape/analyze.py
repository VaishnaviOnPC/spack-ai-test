import spack.repo
from ai_test.config import get as get_config
from ai_test.extract.schema import DependencyInfo
from ai_test.mape.schema import MapeContext, RiskDep

ALPHA = 2.0


def get_compilers():
    try:
        import spack.compilers.config as cc
        installed = [c.format("{name}@{version}") for c in cc.all_compilers()]
    except (ImportError, AttributeError):
        import spack.config
        entries = spack.config.get("compilers") or []
        installed = [e["compiler"]["spec"] for e in entries if "compiler" in e]
    ci_compilers = get_config().get("ci_compilers", [])
    extras = [c for c in ci_compilers if c not in installed]
    return installed, installed + extras


def _has_no_upper_bound(bound: str) -> bool:
    if not bound or bound == ":":
        return True
    parts = bound.split(":")
    return len(parts) == 2 and parts[1] == ""


def _is_cxx_sensitive(dep: DependencyInfo) -> bool:
    return dep.name == "cxx" or "cxx" in (dep.dep_type or [])


def _major_crossings(dep_name: str, bound: str) -> int:
    if not _has_no_upper_bound(bound):
        return 0
    if spack.repo.PATH.is_virtual(dep_name):
        return 0
    try:
        pkg_class = spack.repo.PATH.get_pkg_class(dep_name)
        versions = list(getattr(pkg_class, "versions", {}).keys())
        min_str = bound.lstrip("@").split(":")[0] if bound else ""
        min_major = int(min_str.split(".")[0]) if min_str and min_str.split(".")[0].isdigit() else 0
        above = {int(str(v).split(".")[0]) for v in versions
                 if str(v).split(".")[0].isdigit() and int(str(v).split(".")[0]) > min_major}
        return len(above)
    except spack.repo.UnknownPackageError:
        return 0


def _failure_rate(kb_entries) -> float:
    validated = [e for e in kb_entries if e.validation_status == "validated"]
    if not validated:
        return 0.0
    failed = sum(1 for e in validated if not e.concretized)
    return failed / len(validated)


def score_dep(dep: DependencyInfo, failure_rate: float = 0.0):
    crossings = _major_crossings(dep.name, dep.bound)
    is_unbound = _has_no_upper_bound(dep.bound)
    is_cxx = _is_cxx_sensitive(dep)
    is_virt = spack.repo.PATH.is_virtual(dep.name)

    structural = (
        (2 if is_unbound else 1)
        * (1 + min(crossings, 3))
        * (2 if is_cxx else 1)
        * (2 if is_virt else 1)
    )
    score = (1 + ALPHA * failure_rate) * structural

    notes = []
    if is_unbound:
        notes.append("no upper bound")
    if crossings > 0:
        notes.append(f"{crossings} major crossing{'s' if crossings > 1 else ''}")
    if is_virt:
        notes.append("virtual")
    if is_cxx:
        notes.append("C++ ABI")

    return score, notes


def analyze(context: MapeContext):
    schema = context.package_schema
    failure_rate = _failure_rate(context.kb_entries)

    seen = {}
    for dep in schema.dependencies:
        seen.setdefault(dep.name, dep)

    risk_list = []
    for name, dep in seen.items():
        s, n = score_dep(dep, failure_rate)
        risk_list.append(RiskDep(name=name, score=s, when=dep.when, notes=n))
    risk_deps = sorted(risk_list, key=lambda r: r.score, reverse=True)

    installed, all_compilers = get_compilers()
    return risk_deps, installed, all_compilers, failure_rate

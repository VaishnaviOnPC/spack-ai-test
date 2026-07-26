import spack.repo
from ai_test.config import get as get_config
from ai_test.extract.schema import DependencyInfo
from ai_test.mape.schema import MapeContext, RiskDep

_DEFAULT_CI_COMPILERS = [
    "gcc@11.4.0",
    "gcc@12.3.0",
    "clang@14.0.0",
    "clang@15.0.7",
    "intel@2024.0.0",
]

ALPHA = 2.0


def get_compilers():
    installed = []
    try:
        import spack.compilers.config as cc
        installed = [c.format("{name}@{version}") for c in cc.all_compilers()]
    except Exception:
        import spack.config
        entries = spack.config.get("compilers") or []
        installed = [e["compiler"]["spec"] for e in entries if "compiler" in e]
    ci_compilers = get_config().get("ci_compilers", _DEFAULT_CI_COMPILERS)
    extras = [c for c in ci_compilers if c not in installed]
    return installed, installed + extras


def _has_no_upper_bound(bound: str) -> bool:
    if not bound or bound == ":":
        return True
    parts = bound.split(":")
    return len(parts) == 2 and parts[1] == ""


def _is_virtual(name: str) -> bool:
    return spack.repo.PATH.is_virtual(name)


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
    except Exception:
        return 0


def _failure_rate(kb_entries) -> float:
    validated = [e for e in kb_entries if e.validation_status == "validated"]
    if not validated:
        return 0.0
    failed = sum(1 for e in validated if not e.concretized)
    return failed / len(validated)


def score_dep(dep: DependencyInfo, failure_rate: float = 0.0) -> float:
    crossings = _major_crossings(dep.name, dep.bound)
    structural = (
        (2 if _has_no_upper_bound(dep.bound) else 1)
        * (1 + min(crossings, 3))
        * (2 if _is_cxx_sensitive(dep) else 1)
        * (2 if _is_virtual(dep.name) else 1)
    )
    return (1 + ALPHA * failure_rate) * structural


def analyze(context: MapeContext):
    schema = context.package_schema
    failure_rate = _failure_rate(context.kb_entries)

    seen = {}
    for dep in schema.dependencies:
        seen.setdefault(dep.name, dep)

    risk_deps = sorted(
        [RiskDep(name=name, score=score_dep(dep, failure_rate), when=dep.when) for name, dep in seen.items()],
        key=lambda r: r.score,
        reverse=True,
    )
    installed, all_compilers = get_compilers()
    return risk_deps, installed, all_compilers, failure_rate

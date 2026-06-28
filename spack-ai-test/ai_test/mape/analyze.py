import re
import subprocess
from typing import List, Tuple

from ai_test.extract.schema import DependencyInfo, PackageSchema
from ai_test.mape.schema import MapeContext, RiskDep


# compilers we want in CI even if they're not installed locally
DEFAULT_CI_COMPILERS = [
    "gcc@11.4.0",
    "gcc@12.3.0",
    "clang@14.0.0",
    "clang@15.0.7",
    "intel@2024.0.0",
]


def get_compilers() -> Tuple[List[str], List[str]]:
    result = subprocess.run(["spack", "compilers"], capture_output=True, text=True)
    installed = re.findall(r'\b\w+@[\d]+\.[\d.]+\b', result.stdout)
    extras = [c for c in DEFAULT_CI_COMPILERS if c not in installed]
    return installed, installed + extras


def _has_no_upper_bound(bound: str) -> bool:
    if not bound or bound == ":":
        return True
    parts = bound.split(":")
    return len(parts) == 2 and parts[1] == ""


def _is_virtual(name: str) -> bool:
    try:
        import spack.repo
        return spack.repo.PATH.is_virtual(name)
    except Exception:
        return name in {"mpi", "blas", "lapack", "scalapack", "fftw", "opencl", "c", "cxx"}


def _is_cxx_sensitive(dep: DependencyInfo) -> bool:
    return dep.name == "cxx" or "cxx" in (dep.dep_type or [])


def _major_version_span(dep_name: str) -> int:
    try:
        import spack.repo
        if spack.repo.PATH.is_virtual(dep_name):
            return 0
        pkg_class = spack.repo.PATH.get_pkg_class(dep_name)
        versions = list(getattr(pkg_class, "versions", {}).keys())
        majors = {int(str(v).split(".")[0]) for v in versions if str(v).split(".")[0].isdigit()}
        return 1 if len(majors) > 1 else 0
    except Exception:
        return 0


def score_dep(dep: DependencyInfo) -> float:
    # priority score: (1+unbounded) * (1+multi_major) * (1+cxx) * (1+virtual), max=16
    unbounded = 1 if _has_no_upper_bound(dep.bound) else 0
    multi_major = _major_version_span(dep.name)
    cxx = 1 if _is_cxx_sensitive(dep) else 0
    virtual = 1 if _is_virtual(dep.name) else 0
    return float((1 + unbounded) * (1 + multi_major) * (1 + cxx) * (1 + virtual))


def analyze(context: MapeContext) -> Tuple[List[RiskDep], List[str], List[str]]:
    schema = context.package_schema

    # deduplicate deps by name before scoring
    seen = {}
    for dep in schema.dependencies:
        seen.setdefault(dep.name, dep)

    risk_deps = sorted(
        [RiskDep(name=name, score=score_dep(dep), when=dep.when) for name, dep in seen.items()],
        key=lambda r: r.score,
        reverse=True,
    )
    installed, all_compilers = get_compilers()
    return risk_deps, installed, all_compilers

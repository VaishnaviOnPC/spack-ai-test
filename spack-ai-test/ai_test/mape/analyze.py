import re
import subprocess
from typing import List, Tuple

from ai_test.extract.schema import DependencyInfo, PackageSchema
from ai_test.mape.schema import MapeContext, RiskDep


# Compilers commonly used in HPC/CI environments.
# Specs targeting these are queued for CI even if not installed locally.
CURATED_CI_COMPILERS = [
    "gcc@11.4.0",
    "gcc@12.3.0",
    "clang@14.0.0",
    "clang@15.0.7",
    "intel@2024.0.0",
]


def get_compilers() -> Tuple[List[str], List[str]]:
    result = subprocess.run(["spack", "compilers"], capture_output=True, text=True)
    installed = re.findall(r'\b\w+@[\d]+\.[\d.]+\b', result.stdout)
    extras = [c for c in CURATED_CI_COMPILERS if c not in installed]
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
    # Cold-start Priority(A -> B) = (1+U) x (1+M) x (1+C) x (1+P)  [max = 16]
    U = 1 if _has_no_upper_bound(dep.bound) else 0
    M = _major_version_span(dep.name)
    C = 1 if _is_cxx_sensitive(dep) else 0
    P = 1 if _is_virtual(dep.name) else 0
    return float((1 + U) * (1 + M) * (1 + C) * (1 + P))


def analyze(context: MapeContext) -> Tuple[List[RiskDep], List[str], List[str]]:
    schema = context.package_schema

    seen = {}
    for dep in schema.dependencies:
        seen.setdefault(dep.name, dep)
    risk_deps = sorted(
        [RiskDep(name=name, score=score_dep(dep), when=dep.when) for name, dep in seen.items()],
        key=lambda r: r.score,
        reverse=True,
    )
    installed_compilers, all_compilers = get_compilers()
    return risk_deps, installed_compilers, all_compilers

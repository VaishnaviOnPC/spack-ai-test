from typing import List
import spack.repo
from ai_test.extract.schema import RiskSignals

_LANGUAGE_MARKERS = {"python", "r", "java", "perl", "ruby", "lua"}

_STANDARD_BUILD_SYSTEMS = {
    "CMakePackage", "AutotoolsPackage", "MesonPackage",
    "QMakePackage", "WafPackage", "MakefilePackage",
    "PythonPackage", "RPackage", "PerlPackage", "SCons",
}

_FORTRAN_ABI_MARKERS = {"mpi", "blas", "lapack", "scalapack", "fftw"}


def _cross_language_bindings(dep_names: set) -> bool:
    hits = set()
    for marker in _LANGUAGE_MARKERS:
        if any(d == marker or d.startswith(marker + "-") for d in dep_names):
            hits.add(marker)
    if dep_names & {"cuda", "hip", "rocm"} and dep_names & _FORTRAN_ABI_MARKERS:
        hits.update({"gpu", "fortran-abi"})
    return len(hits) >= 2


def _custom_build_system(pkg_class) -> bool:
    mro_names = {c.__name__ for c in pkg_class.__mro__}
    return not bool(mro_names & _STANDARD_BUILD_SYSTEMS)


def _compiler_conflicts(pkg_class) -> int:
    return sum(1 for key in getattr(pkg_class, "conflicts", {}) if "%" in str(key))


def virtual_dependencies(pkg_class) -> List[str]:
    virtuals = []
    repo = spack.repo.PATH
    for _when, dep_dict in getattr(pkg_class, "dependencies", {}).items():
        if not isinstance(dep_dict, dict):
            continue
        for name_key in dep_dict:
            name = str(name_key)
            if repo.is_virtual(name):
                virtuals.append(name)
    return sorted(set(virtuals))


def compute_signals(pkg_class, virtual_deps: List[str]) -> RiskSignals:
    dep_names = set()
    for _when, dep_dict in getattr(pkg_class, "dependencies", {}).items():
        if isinstance(dep_dict, dict):
            dep_names.update(str(k) for k in dep_dict)

    return RiskSignals(
        cross_language_bindings=_cross_language_bindings(dep_names),
        custom_build_system=_custom_build_system(pkg_class),
        compiler_conflict_count=_compiler_conflicts(pkg_class),
        virtual_provider_count=len(virtual_deps),
    )
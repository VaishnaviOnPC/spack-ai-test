from typing import Optional

from ai_test.extract.schema import PackageSchema, RiskSignals, VariantInfo, DependencyInfo
from ai_test.extract.reader import (
    get_pkg_class,
    extract_versions,
    extract_variants,
    extract_dependencies,
    extract_conflicts,
)
from ai_test.extract.signals import compute_signals, virtual_dependencies
from ai_test.extract.canonical import write_canonical, read_canonical


def extract(pkg_name: str, output_path: Optional[str] = None) -> PackageSchema:
    pkg_class = get_pkg_class(pkg_name)
    virtual_deps = virtual_dependencies(pkg_class)

    schema = PackageSchema(
        name=pkg_name,
        versions=extract_versions(pkg_class),
        variants=extract_variants(pkg_class),
        dependencies=extract_dependencies(pkg_class),
        declared_conflicts=extract_conflicts(pkg_class),
        virtual_deps=virtual_deps,
        risk_signals=compute_signals(pkg_class, virtual_deps),
    )

    if output_path is not None:
        write_canonical(schema, output_path)

    return schema
from typing import Optional
from ai_test.extract.schema import PackageSchema


def _yn(value):
    return "Yes" if value else "No"


def print_schema(schema: PackageSchema, output_path: Optional[str] = None):
    print()
    print("Package: " + schema.name)

    versions = schema.versions
    if versions:
        print("Versions: " + ", ".join(versions))
    else:
        print("Versions: none found")

    print()
    print("Variants (" + str(len(schema.variants)) + "):")
    if schema.variants:
        for name, v in sorted(schema.variants.items()):
            line = name + " (default=" + str(v.default) + ")"
            if v.description:
                line += " : " + v.description
            if v.when:
                line += " [when: " + v.when + "]"
            if v.values:
                line += " [values: " + str(v.values) + "]"
            print(line)
    else:
        print("  none")

    seen = {}
    for dep in schema.dependencies:
        if dep.name not in seen:
            seen[dep.name] = dep

    print()
    print("Dependencies (" + str(len(seen)) + "):")
    if seen:
        for dep in sorted(seen.values(), key=lambda d: d.name):
            line = dep.name
            if dep.bound and dep.bound != ":":
                line += " @" + dep.bound
            if dep.dep_type:
                line += " [" + ", ".join(dep.dep_type) + "]"
            if dep.when:
                line += ", when: " + dep.when
            print(line)
    else:
        print("  none")

    print()
    print("Declared Conflicts (" + str(len(schema.declared_conflicts)) + "):")
    if schema.declared_conflicts:
        for entry in schema.declared_conflicts:
            for spec, when in entry.items():
                print(spec + " (when: " + when + ")")
    else:
        print("  none")

    if schema.virtual_deps:
        print()
        print("Virtual deps: " + ", ".join(schema.virtual_deps))

    rs = schema.risk_signals
    print()
    print("Risk Signals:")
    print("Cross-language bindings: " + _yn(rs.cross_language_bindings))
    print("Custom build system: " + _yn(rs.custom_build_system))
    print("Compiler conflicts declared: " + str(rs.compiler_conflict_count))
    print("Virtual providers needed: " + str(rs.virtual_provider_count))
    print()
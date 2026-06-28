import json
import re

from ai_test.extract.schema import PackageSchema
from ai_test.llm.client import LLMClient
from ai_test.llm.prompt import build_messages
from ai_test.llm.schema import LLMResponse


def _package_context(schema: PackageSchema) -> str:
    versions = schema.versions[:5]
    versions_str = ", ".join(versions)
    if len(schema.versions) > 5:
        versions_str += f" (+{len(schema.versions) - 5} more)"

    lines = [
        f"Package: {schema.name}",
        f"Versions: {versions_str or 'none declared'}",
        f"Variants ({len(schema.variants)}):",
    ]
    for name, v in sorted(schema.variants.items()):
        line = f"  {name} (default={v.default})"
        if v.description:
            line += f": {v.description}"
        if v.when:
            line += f" [when: {v.when}]"
        lines.append(line)
    return "\n".join(lines)


def _risk_context(schema: PackageSchema, dep_scores=None, compilers=None) -> str:
    if dep_scores is not None:
        lines = ["Dependency risk scores (Priority = (1+U)x(1+M)x(1+C)x(1+P), max=16):"]
        for dep in sorted(dep_scores, key=lambda d: d.score, reverse=True):
            cond = f" [when: {dep.when}]" if dep.when else ""
            lines.append(f"  {dep.name}: {dep.score:.1f}{cond}")
        if compilers:
            lines.append(f"\nAvailable compilers: {', '.join(compilers)}")
        lines.append("\nFocus on variant combinations that activate the highest-scoring dependencies.")
        lines.append("Version failures from deterministic sweep: not yet available (Stage 2 pending)")
        return "\n".join(lines)

    rs = schema.risk_signals
    lines = ["Structural signals (potential CI coverage gaps):"]
    if rs.cross_language_bindings:
        lines.append("- Cross-language bindings — multi-toolchain combinations rarely tested together")
    if rs.custom_build_system:
        lines.append("- Custom build system — compiler flag handling may differ from standard packages")
    if rs.compiler_conflict_count:
        lines.append(f"- {rs.compiler_conflict_count} declared compiler conflicts — adjacent versions may have undeclared issues")
    if rs.virtual_provider_count:
        lines.append(f"- Virtual providers needed: {', '.join(schema.virtual_deps)}")
    lines.append("\nVersion failures: not yet available (Stage 2 pending)")
    return "\n".join(lines)


def _conflict_context(schema: PackageSchema) -> str:
    if not schema.declared_conflicts:
        return "Declared conflicts: none"
    lines = [f"Declared conflicts ({len(schema.declared_conflicts)}):"]
    for entry in schema.declared_conflicts[:15]:
        for spec, when in entry.items():
            lines.append(f"  conflicts({spec!r}, when={when!r})")
    if len(schema.declared_conflicts) > 15:
        lines.append(f"  ... ({len(schema.declared_conflicts) - 15} more)")
    return "\n".join(lines)


def _parse(package: str, raw: str) -> LLMResponse:
    cleaned = re.sub(r"```json|```", "", raw).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return LLMResponse(package=package, risk_level="unknown", concerns=[], suggested_specs=[], raw=raw)
    scenarios = data.get("test_scenarios", [])
    if scenarios and isinstance(scenarios[0], dict):
        specs = [s["spec"] for s in scenarios if "spec" in s]
    else:
        specs = [str(s) for s in scenarios]
    return LLMResponse(package=package, risk_level="unknown", concerns=[], suggested_specs=specs, raw=raw)


def analyze(schema: PackageSchema, model="claude-sonnet-4-6", dep_scores=None, compilers=None) -> LLMResponse:
    client = LLMClient(model=model)
    messages = build_messages(
        package_context=_package_context(schema),
        risk_context=_risk_context(schema, dep_scores, compilers),
        reference_context="Reference packages: not yet available",
        conflict_context=_conflict_context(schema),
        compilers=compilers,
    )
    raw = client.ask(messages)
    return _parse(schema.name, raw)

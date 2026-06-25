import json
import re

from ai_test.extract.schema import PackageSchema
from ai_test.llm.client import LLMClient
from ai_test.llm.prompt import build_messages, repair_message
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


def _risk_context(schema: PackageSchema) -> str:
    rs = schema.risk_signals
    lines = ["Structural signals (potential CI coverage gaps):"]
    if rs.cross_language_bindings:
        lines.append("- Cross-language bindings: multi-toolchain combinations rarely tested together")
    if rs.custom_build_system:
        lines.append("- Custom build system: compiler flag handling may differ from standard packages")
    if rs.compiler_conflict_count:
        lines.append(f"- {rs.compiler_conflict_count} declared compiler conflicts: adjacent versions may have undeclared issues")
    if rs.virtual_provider_count:
        lines.append(f"- Virtual providers needed: {', '.join(schema.virtual_deps)} — provider version combinations are rarely exhaustively tested")
    if len(lines) == 1:
        lines.append("- None detected")

    lines.append("\nVersion failures from deterministic sweep: not yet available (Stage 2 pending)")
    lines.append("Scored off-leading-edge pairs: not yet available (requires mape/analyze.py)")
    return "\n".join(lines)


def _reference_context() -> str:
    # Placeholder — mape/analyze.py will retrieve structurally similar packages
    # and pass their metadata here as Layer 3.
    return "Reference packages: not yet available (requires structural retrieval step)"


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
        scenarios = data.get("test_scenarios", [])
        if scenarios and isinstance(scenarios[0], dict):
            specs = [s["spec"] for s in scenarios if "spec" in s]
        else:
            specs = [str(s) for s in scenarios]
    except (json.JSONDecodeError, KeyError):
        specs = []
    return LLMResponse(package=package, risk_level="unknown", concerns=[], suggested_specs=specs, raw=raw)


def analyze(schema: PackageSchema, model="claude-sonnet-4-6") -> LLMResponse:
    client = LLMClient(model=model)
    messages = build_messages(
        package_context=_package_context(schema),
        risk_context=_risk_context(schema),
        reference_context=_reference_context(),
        conflict_context=_conflict_context(schema),
    )
    raw = client.ask(messages)
    return _parse(schema.name, raw)

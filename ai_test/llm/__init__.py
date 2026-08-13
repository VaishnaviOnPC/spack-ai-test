import json
import re

from ai_test.extract.schema import PackageSchema
from ai_test.llm.client import LLMClient
from ai_test.llm.prompt import build_messages
from ai_test.llm.schema import LLMResponse


def _pkg_summary(schema: PackageSchema) -> str:
    versions_str = ", ".join(schema.versions[:5])
    if len(schema.versions) > 5:
        versions_str += f" (+{len(schema.versions) - 5} more)"

    lines = [
        f"Package: {schema.name}",
        f"Versions: {versions_str or 'none declared'}",
        f"Variants ({len(schema.variants)}):",
    ]
    for name, v in sorted(schema.variants.items()):
        line = f"  {name} (default={v.default})"
        if v.values:
            line += f" [values: {', '.join(str(val) for val in v.values)}]"
        if v.description:
            line += f": {v.description}"
        if v.when:
            line += f" [when: {v.when}]"
        lines.append(line)
    return "\n".join(lines)


def _risk_summary(schema: PackageSchema, dep_scores=None, compilers=None) -> str:
    if dep_scores is not None:
        lines = ["Dependency risk scores (higher = more likely to break, max=16):"]
        for dep in sorted(dep_scores, key=lambda d: d.score, reverse=True):
            cond = f" [when: {dep.when}]" if dep.when else ""
            lines.append(f"  {dep.name}: {dep.score:.1f}{cond}")
        if compilers:
            lines.append(f"\nAvailable compilers: {', '.join(compilers)}")
        lines.append("\nFocus on variant combinations that activate the highest-scoring dependencies.")
        return "\n".join(lines)

    rs = schema.risk_signals
    lines = ["Structural signals (potential CI coverage gaps):"]
    if rs.cross_language_bindings:
        lines.append("- Cross-language bindings: multi-toolchain combinations rarely tested together")
    if rs.custom_build_system:
        lines.append("- Custom build system: compiler flag handling may differ from standard packages")
    if rs.compiler_conflict_count:
        lines.append(f"- {rs.compiler_conflict_count} declared compiler conflicts: adjacent versions may have undeclared issues")
    if rs.virtual_provider_count:
        lines.append(f"- Virtual providers needed: {', '.join(schema.virtual_deps)}")
    return "\n".join(lines)


def _conflicts(schema: PackageSchema) -> str:
    if not schema.declared_conflicts:
        return "Declared conflicts: none"
    lines = [f"Declared conflicts ({len(schema.declared_conflicts)}):"]
    for entry in schema.declared_conflicts[:15]:
        for spec, when in entry.items():
            lines.append(f"  conflicts({spec!r}, when={when!r})")
    if len(schema.declared_conflicts) > 15:
        lines.append(f"  (+{len(schema.declared_conflicts) - 15} more)")
    return "\n".join(lines)


def _failed_specs_context(pkg_name: str, kb_path: str | None) -> str | None:
    if not kb_path:
        return None
    from ai_test.kb.store import load as load_kb
    entries = load_kb(kb_path)

    bad = [
        e for e in entries
        if e.pkg_name == pkg_name
        and not e.concretized
        and e.failure_reason
    ]
    if not bad:
        return None

    lines = [
        f"The following {pkg_name} specs failed to concretize or were rejected in "
        "previous runs. Do NOT generate these exact specs again. Review the rejection "
        "reasons and avoid the specific conflict that caused the failure:"
    ]
    for e in bad[-20:]:
        reason = e.failure_reason.splitlines()[0] if e.failure_reason else "unknown"
        lines.append(f"  {e.spec}  # reason: {reason}")
    return "\n".join(lines)


def _parse(package: str, raw: str) -> LLMResponse:
    cleaned = re.sub(r"```json|```", "", raw).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return LLMResponse(package=package, suggested_specs=[], raw=raw)
    scenarios = data.get("test_scenarios", [])
    if scenarios and isinstance(scenarios[0], dict):
        specs = [s["spec"] for s in scenarios if "spec" in s]
    else:
        specs = [str(s) for s in scenarios]
    return LLMResponse(package=package, suggested_specs=specs, raw=raw)


def analyze(
    schema: PackageSchema,
    model="claude-haiku-4-5",
    dep_scores=None,
    compilers=None,
    kb_path: str | None = None,
) -> LLMResponse:
    failed_ctx = _failed_specs_context(schema.name, kb_path)
    messages = build_messages(
        _pkg_summary(schema),
        _risk_summary(schema, dep_scores, compilers),
        _conflicts(schema),
        compilers=compilers,
        failed_specs_ctx=failed_ctx,
    )
    return _parse(schema.name, LLMClient(model=model).ask(messages))

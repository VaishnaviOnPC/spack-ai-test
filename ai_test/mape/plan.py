import spack.store

from ai_test.extract.schema import PackageSchema
from ai_test.llm import _pkg_summary, _risk_summary, _conflicts, _parse
from ai_test.llm.client import LLMClient
from ai_test.llm.prompt import get_system_prompt, task_prompt
from ai_test.llm.schema import LLMResponse
from ai_test.mape.retrieval import gap_context, kb_patterns, valid_dep_versions_context


def _installed_ctx(schema: PackageSchema) -> str:
    if not hasattr(spack.store, "STORE") or not spack.store.STORE:
        return ""
    installed = spack.store.STORE.db.query(schema.name)

    if not installed:
        return ""

    lines = ["Locally installed configurations (proven to build):"]
    for spec in installed[:5]:
        lines.append(f"  {spec.short_spec}")
    lines.append("Avoid regenerating these exact configurations.")
    return "\n".join(lines)


def _kb_ctx(schema: PackageSchema, kb_entries: list) -> str:
    if not kb_entries:
        return "KB history: no prior results for this package"

    concretized = [e for e in kb_entries if e.concretized]
    failed_conc = [e for e in kb_entries if not e.concretized and e.failure_reason]
    queued = [e for e in kb_entries if e.validation_status == "ci_queue"]

    lines = [f"KB history for {schema.name} ({len(kb_entries)} entries):"]
    if concretized:
        def _sort_key(e):
            if e.test_passed is False: return 0
            if not e.installed and e.install_error: return 1
            if e.installed: return 2
            return 3
        concretized.sort(key=_sort_key)

        lines.append(
            f"  Concretized specs ({len(concretized)}) - these combinations successfully bypassed the concretizer. "
            "Specs marked [BUILD_FAIL] or [TEST_FAIL] are highly valuable discoveries. "
            "Learn from these patterns to explore the configuration space and find new bugs. "
            "Do NOT regenerate these exact specs:"
        )
        for e in concretized[:5]:
            if e.test_passed is False:
                tag = "[TEST_FAIL]"
            elif not e.installed and e.install_error:
                tag = "[BUILD_FAIL]"
            elif e.installed:
                tag = "[PASS]"
            else:
                tag = "[CONCRETIZED]"
            lines.append(f"    {tag} {e.spec}")
    if failed_conc:
        lines.append(
            f"\n  The following {len(failed_conc)} specs FAILED to concretize - "
            "the concretizer rejected them. Their variant/version patterns are INVALID. "
            "DO NOT generate specs using these patterns:"
        )
        for e in failed_conc[-20:]:
            reason = e.failure_reason.splitlines()[0] if e.failure_reason else "unknown"
            lines.append(f"    {e.spec}  # {reason}")
    if queued:
        lines.append(f"\n  Queued for CI: {len(queued)} specs")
    lines.append("Generate NEW specs not already in KB.")
    return "\n".join(lines)


def call_llm(
    schema: PackageSchema,
    risk_deps,
    all_compilers,
    kb_entries: list,
    model: str,
    retrieval: bool = True,
    auto_patterns: list = None,
    github_signal=None,
    issue_context: str = "",
) -> LLMResponse:
    dep_gap = gap_context(schema) if retrieval else ""
    dep_versions = valid_dep_versions_context(schema) if retrieval else ""
    kb_pattern = kb_patterns(kb_entries) if retrieval else ""
    installed = _installed_ctx(schema)
    kb = _kb_ctx(schema, kb_entries)

    messages = [
        {"role": "system", "content": get_system_prompt(auto_patterns=auto_patterns)},
        {"role": "user", "content": _pkg_summary(schema)},
        {"role": "user", "content": _risk_summary(schema, risk_deps, all_compilers)},
    ]
    if dep_versions:
        messages.append({"role": "user", "content": dep_versions})
    if dep_gap:
        messages.append({"role": "user", "content": dep_gap})
    if kb_pattern:
        messages.append({"role": "user", "content": kb_pattern})
    if github_signal:
        messages.append({"role": "user", "content": (
            f"GitHub activity for {schema.name} (upstream: {github_signal.slug}): "
            f"{github_signal.open_issues} open issues, {github_signal.open_prs} open PRs. "
            "This indicates an actively-changing package - prioritize testing variant "
            "combinations and older versions that may have regressed silently."
        )})
    if issue_context:
        messages.append({"role": "user", "content": (
            issue_context + "\n\nUse these reports to guide your spec generation: "
            "prefer versions, variants, and compiler combinations that appear in failing "
            "reports. Do not reproduce specs that are working; explore the boundaries "
            "around the reported failures."
        )})
    if installed:
        messages.append({"role": "user", "content": installed})
    messages += [
        {"role": "user", "content": kb},
        {"role": "user", "content": _conflicts(schema)},
        {"role": "user", "content": task_prompt(all_compilers)},
    ]

    raw = LLMClient(model=model).ask(messages)
    return _parse(schema.name, raw)

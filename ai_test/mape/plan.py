import spack.store

from ai_test.extract.schema import PackageSchema
from ai_test.llm import _pkg_summary, _risk_summary, _conflicts, _parse
from ai_test.llm.client import LLMClient
from ai_test.llm.prompt import SYSTEM_PROMPT, task_prompt
from ai_test.llm.schema import LLMResponse
from ai_test.mape.retrieval import find_similar, get_chunks


def _similar_pkgs_ctx(schema: PackageSchema) -> str:
    similar = find_similar(schema, top_n=2)
    if not similar:
        return "Similar packages: none found"

    lines = ["Structurally similar packages (syntax examples from package.py):"]
    for pkg_name, score in similar:
        lines.append(f"  {pkg_name} (similarity {score:.3f}):")
        chunks = get_chunks(pkg_name)
        if chunks:
            for line in chunks.splitlines():
                lines.append(f"    {line}")
    lines.append("Use these as concrete examples for realistic spec patterns.")
    return "\n".join(lines)


def _similar_kb_ctx(schema: PackageSchema, kb_path: str) -> str:
    from ai_test.kb.store import load as load_kb

    similar = find_similar(schema, top_n=3)
    if not similar:
        return ""

    all_entries = load_kb(kb_path)
    by_pkg = {}
    for entry in all_entries:
        by_pkg.setdefault(entry.pkg_name, []).append(entry)

    lines = ["Cross-package KB evidence (structurally similar packages):"]
    found_any = False

    for pkg_name, score in similar:
        entries = [e for e in by_pkg.get(pkg_name, []) if e.validation_status == "validated"]
        if not entries:
            continue
        found_any = True
        passed = [e for e in entries if e.concretized][:2]
        failed = [e for e in entries if not e.concretized and e.failure_reason][:2]
        lines.append(f"  {pkg_name} (similarity {score:.2f}):")
        for e in passed:
            lines.append(f"    [OK]   {e.spec}")
        for e in failed:
            reason = e.failure_reason.splitlines()[0]
            lines.append(f"    [FAIL] {e.spec}  # {reason}")

    if not found_any:
        return ""

    lines.append("Prefer spec patterns that succeeded in similar packages.")
    return "\n".join(lines)


def _installed_ctx(schema: PackageSchema) -> str:
    try:
        installed = spack.store.STORE.db.query(schema.name)
    except Exception:
        return ""

    if not installed:
        return ""

    lines = ["Locally installed configurations (proven to build):"]
    for spec in installed[:5]:
        lines.append(f"  {spec.short_spec}")
    lines.append("Prefer generating specs that resemble these proven configurations.")
    return "\n".join(lines)


def _kb_ctx(schema: PackageSchema, kb_entries: list) -> str:
    if not kb_entries:
        return "KB history: no prior results for this package"

    passed = [e for e in kb_entries if e.concretized]
    failed = [e for e in kb_entries if not e.concretized and e.failure_reason]
    queued = [e for e in kb_entries if e.validation_status == "ci_queue"]

    lines = [f"KB history for {schema.name} ({len(kb_entries)} entries):"]
    if passed:
        lines.append(f"  Concretized OK ({len(passed)}) — do not regenerate these:")
        for e in passed[:3]:
            lines.append(f"    {e.spec}")
    if failed:
        lines.append(f"  Known failures ({len(failed)}):")
        for e in failed[:3]:
            reason = e.failure_reason.splitlines()[0]
            lines.append(f"    {e.spec}  →  {reason}")
    if queued:
        lines.append(f"  Queued for CI: {len(queued)} specs")
    lines.append("Generate NEW specs not already in KB. Avoid patterns similar to known failures.")
    return "\n".join(lines)


def call_llm(
    schema: PackageSchema,
    risk_deps,
    all_compilers,
    kb_entries: list,
    model: str,
    kb_path: str = None,
    retrieval: bool = True,
) -> LLMResponse:
    similar_syntax = _similar_pkgs_ctx(schema) if retrieval else ""
    similar_kb = _similar_kb_ctx(schema, kb_path) if (retrieval and kb_path) else ""
    installed = _installed_ctx(schema)
    kb = _kb_ctx(schema, kb_entries)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _pkg_summary(schema)},
        {"role": "user", "content": _risk_summary(schema, risk_deps, all_compilers)},
        {"role": "user", "content": similar_syntax},
    ]
    if similar_kb:
        messages.append({"role": "user", "content": similar_kb})
    if installed:
        messages.append({"role": "user", "content": installed})
    messages += [
        {"role": "user", "content": kb},
        {"role": "user", "content": _conflicts(schema)},
        {"role": "user", "content": task_prompt(all_compilers)},
    ]

    raw = LLMClient(model=model).ask(messages)
    return _parse(schema.name, raw)

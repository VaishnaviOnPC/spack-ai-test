from ai_test.extract.schema import PackageSchema
from ai_test.llm import _pkg_summary, _risk_summary, _conflicts, _parse
from ai_test.llm.client import LLMClient
from ai_test.llm.prompt import SYSTEM_PROMPT, task_prompt
from ai_test.mape.retrieval import find_similar, get_chunks


def _similar_pkgs_ctx(schema: PackageSchema) -> str:
    similar = find_similar(schema, top_n=2)
    if not similar:
        return "Similar packages: none found"

    lines = ["Structurally similar packages:"]
    for pkg_name, score in similar:
        lines.append(f"  {pkg_name} (score: {score:.3f})")
        chunks = get_chunks(pkg_name)
        if chunks:
            lines.append("    from package.py:")
            for line in chunks.splitlines():
                lines.append(f"    {line}")
    lines.append("Use these as concrete examples for realistic spec patterns.")
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
            lines.append(f"    {e.spec}: {reason}")
    if queued:
        lines.append(f"  Queued for CI: {len(queued)} specs")
    lines.append("Generate NEW specs not already in KB. Avoid patterns similar to known failures.")
    return "\n".join(lines)


def call_llm(schema, risk_deps, all_compilers, kb_entries, model):
    similar = _similar_pkgs_ctx(schema)
    kb = _kb_ctx(schema, kb_entries)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _pkg_summary(schema)},
        {"role": "user", "content": _risk_summary(schema, risk_deps, all_compilers)},
        {"role": "user", "content": similar},
        {"role": "user", "content": kb},
        {"role": "user", "content": _conflicts(schema)},
        {"role": "user", "content": task_prompt(all_compilers)},
    ]
    raw = LLMClient(model=model).ask(messages)
    return _parse(schema.name, raw)

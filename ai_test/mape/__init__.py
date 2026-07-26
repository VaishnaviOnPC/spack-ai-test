from ai_test.mape.analyze import analyze as analyze_deps
from ai_test.mape.execute import execute_all
from ai_test.mape.monitor import load_context
from ai_test.mape.plan import call_llm


def run(pkg_name: str, kb_path: str, model: str = "claude-haiku-4-5", build: bool = False, local: bool = False, compiler: str = None, retrieval: bool = True):
    context = load_context(pkg_name, kb_path)
    schema = context.package_schema
    risk_deps, installed_compilers, all_compilers, failure_rate = analyze_deps(context)

    validated = [e for e in context.kb_entries if e.validation_status == "validated"]
    if validated:
        failed_count = sum(1 for e in validated if not e.concretized)
        rate_str = f"failure rate: {failure_rate:.2f} ({failed_count}/{len(validated)})"
    else:
        rate_str = "no KB history"

    if compiler:
        compiler_str = f"compiler: {compiler}"
        compilers_for_plan = [compiler]
    elif local:
        compiler_str = "local compilers only"
        compilers_for_plan = installed_compilers
    else:
        compiler_str = f"{len(all_compilers)} compilers"
        compilers_for_plan = all_compilers

    retrieval_str = "" if retrieval else " | no retrieval"
    print(f"\n{schema.name} | KB: {len(context.kb_entries)} entries | {rate_str} | {compiler_str}{retrieval_str}")

    if not installed_compilers:
        print("(hint: run 'spack compiler find' to register compilers)")

    print(f"Generating specs via {model}...")
    llm_result = call_llm(schema, risk_deps, compilers_for_plan, context.kb_entries, model, retrieval=retrieval)

    if not llm_result.suggested_specs:
        print("LLM did not return parseable specs.")
        print(llm_result.raw)
        return

    if build:
        print("(--build: concretized specs will also run spack install)")

    results = execute_all(
        llm_result.suggested_specs,
        schema,
        kb_path,
        installed_compilers=installed_compilers,
        model=model,
        build=build,
    )

    ci = [r for r in results if not r.concretized and r.failure_reason is None]
    failed = [r for r in results if not r.concretized and r.failure_reason is not None]
    passed = [r for r in results if r.concretized]
    built = [r for r in results if r.installed]

    parts = [f"{len(passed) + len(failed)} tested", f"{len(passed)} concretized", f"{len(failed)} failed"]
    if build:
        parts.append(f"{len(built)} built")
    if ci:
        ci_needed = [c for c in all_compilers if c not in installed_compilers]
        parts.append(f"{len(ci)} queued for CI ({', '.join(ci_needed)})")
    print(f"\n{' | '.join(parts)} : {kb_path}")

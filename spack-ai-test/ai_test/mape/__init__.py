from ai_test.llm import analyze as llm_analyze
from ai_test.mape.analyze import analyze as analyze_deps
from ai_test.mape.execute import execute_all
from ai_test.mape.monitor import load_context


def run(pkg_name: str, kb_path: str, model: str = "claude-haiku-4-5"):
    print()
    print("--- Monitor ---")
    context = load_context(pkg_name, kb_path)
    schema = context.package_schema
    print(f"Package: {schema.name}  (known KB entries: {len(context.kb_entries)})")

    print()
    print("--- Analyze ---")
    risk_deps, installed_compilers, all_compilers = analyze_deps(context)
    for dep in risk_deps:
        cond = f"  [when: {dep.when}]" if dep.when else ""
        print(f"  {dep.name}: {dep.score:.1f}/16.0{cond}")
    print(f"Installed compilers:  {', '.join(installed_compilers) or 'none'}")
    print(f"CI compiler set:      {', '.join(all_compilers)}")

    print()
    print("--- Plan ---")
    llm_result = llm_analyze(schema, model=model, dep_scores=risk_deps, compilers=all_compilers)

    if not llm_result.suggested_specs:
        print("LLM did not return parseable specs.")
        print(llm_result.raw)
        return

    print(f"Generated {len(llm_result.suggested_specs)} candidate specs.")

    print()
    print("--- Execute ---")
    results = execute_all(
        llm_result.suggested_specs,
        schema,
        kb_path,
        installed_compilers=installed_compilers,
        model=model,
    )

    ci      = [r for r in results if not r.concretized and r.failure_reason is None]
    failed  = [r for r in results if not r.concretized and r.failure_reason is not None]
    passed  = [r for r in results if r.concretized]

    print()
    print("--- Results ---")
    print(f"Validated locally:  {len(passed) + len(failed)}")
    print(f"  Concretized:      {len(passed)}")
    print(f"  Failed:           {len(failed)}")
    if ci:
        ci_needed = [c for c in all_compilers if c not in installed_compilers]
        print(f"CI queue:           {len(ci)}  (needs: {', '.join(ci_needed)})")
    print(f"Results saved to KB: {kb_path}")

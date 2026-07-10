from ai_test.mape.analyze import analyze as analyze_deps
from ai_test.mape.execute import execute_all
from ai_test.mape.monitor import load_context
from ai_test.mape.plan import call_llm


def run(pkg_name: str, kb_path: str, model: str = "claude-haiku-4-5", build: bool = False, local: bool = False, compiler: str = None):
    print()
    print("--- Monitor ---")
    context = load_context(pkg_name, kb_path)
    schema = context.package_schema
    print(f"Package: {schema.name} (known KB entries: {len(context.kb_entries)})")

    print()
    print("--- Analyze ---")
    risk_deps, installed_compilers, all_compilers, f_rate = analyze_deps(context)

    validated = [e for e in context.kb_entries if e.validation_status == "validated"]
    if validated:
        failed_count = sum(1 for e in validated if not e.concretized)
        print(f"Package failure rate (KB): {f_rate:.2f} ({failed_count}/{len(validated)} validated)")

    for dep in risk_deps:
        cond = f"  [when: {dep.when}]" if dep.when else ""
        print(f"  {dep.name}: {dep.score:.1f}{cond}")
    print(f"Installed compilers: {', '.join(installed_compilers) or 'none'}")
    if not installed_compilers:
        print("  (hint: run 'spack compiler find' to register compilers)")
    if compiler:
        compilers_for_plan = [compiler]
        print(f"Compiler override: {compiler}")
    elif local:
        compilers_for_plan = installed_compilers
        print("Using local compilers only (--local)")
    else:
        compilers_for_plan = all_compilers
        print(f"CI compiler set: {', '.join(all_compilers)}")

    print()
    print("--- Plan ---")
    print("Querying LLM...")
    llm_result = call_llm(schema, risk_deps, compilers_for_plan, context.kb_entries, model)

    if not llm_result.suggested_specs:
        print("LLM did not return parseable specs.")
        print(llm_result.raw)
        return

    print(f"  Generated {len(llm_result.suggested_specs)} candidate specs.")

    print()
    print("--- Execute ---")
    if build:
        print("  (--build enabled: concretized specs will also run spack install)")
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

    print()
    print("--- Results ---")
    print(f"Validated locally: {len(passed) + len(failed)}")
    print(f"  Concretized: {len(passed)}")
    if build:
        print(f"  Built: {len(built)}")
    print(f"  Failed: {len(failed)}")
    if ci:
        ci_needed = [c for c in all_compilers if c not in installed_compilers]
        print(f"CI queue: {len(ci)}  (needs: {', '.join(ci_needed)})")
    print(f"Results saved to: {kb_path}")

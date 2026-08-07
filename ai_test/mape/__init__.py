import re

from ai_test.mape.analyze import analyze as analyze_deps
from ai_test.mape.execute import execute_all
from ai_test.mape.monitor import load_context
from ai_test.mape.plan import call_llm
from ai_test.mape.retrieval import mine_persistent_patterns


def _parse_features(spec_str: str) -> tuple:
    root = spec_str.split("^")[0].split("%")[0]
    features = []
    for tok in root.split()[1:]:
        if re.match(r"^[+~]\w+$", tok) or re.match(r"^\w+=\S+$", tok):
            features.append(tok)
    dep_pins = re.findall(r"\^([\w\-]+@[\d][^\s^%]*)", spec_str)
    return features, dep_pins


def _kb_feature_stats(kb_entries, feature: str) -> tuple:
    validated = [e for e in kb_entries if e.validation_status == "validated"]
    n, k = 0, 0
    for e in validated:
        if feature in e.spec:
            n += 1
            if not e.concretized:
                k += 1
    return n, k


def _risk_label(score: float) -> str:
    if score >= 16:
        return "HIGH"
    if score >= 6:
        return "MED"
    return "LOW"


def score_spec(spec_str: str, kb_path: str):
    from ai_test.extract import extract
    from ai_test.kb.store import load as load_kb

    pkg_name = re.split(r"[@%+~ ^]", spec_str.strip())[0]

    print(f"\n==> spack ai-test: scoring '{spec_str}'")
    schema = extract(pkg_name)
    all_entries = load_kb(kb_path)
    pkg_entries = [e for e in all_entries if e.pkg_name == pkg_name and e.pkg_hash == schema.sha256]

    from ai_test.mape.schema import MapeContext
    context = MapeContext(package_schema=schema, kb_entries=pkg_entries)
    risk_deps, _, _, failure_rate = analyze_deps(context)

    validated = [e for e in pkg_entries if e.validation_status == "validated"]
    if validated:
        n_failed = sum(1 for e in validated if not e.concretized)
        kb_str = f"{len(pkg_entries)} KB entries, failure rate {failure_rate:.2f} ({n_failed}/{len(validated)})"
    else:
        kb_str = f"{len(pkg_entries)} KB entries, no history yet"

    print(f"    package: {schema.name}")
    print(f"    kb: {kb_str}")

    print("\nDependency risk scores:")
    for rd in risk_deps[:10]:
        label = _risk_label(rd.score)
        notes_str = f"  ({', '.join(rd.notes)})" if rd.notes else ""
        print(f"  {rd.name:<20} {rd.score:>5.1f}  {label}{notes_str}")

    features, dep_pins = _parse_features(spec_str)
    all_features = features + [f"^{p}" for p in dep_pins]

    if all_features and validated:
        print("\nVariant/dep failure history:")
        rows = []
        for feat in all_features:
            n, k = _kb_feature_stats(pkg_entries, feat)
            if n >= 2:
                pct = k / n * 100
                label = "HIGH" if pct >= 85 else ("MED" if pct >= 50 else "LOW")
                rows.append(f"  {feat:<30} {k}/{n} failures ({pct:.0f}%)  {label}")
        if rows:
            for row in rows:
                print(row)
        else:
            print("  no KB history for these features yet")
    elif all_features:
        print("\n  no KB history yet, variant pattern analysis unavailable")

    if risk_deps:
        top = risk_deps[0]
        print(f"\nOverall risk: {_risk_label(top.score)} (top dep: {top.name}, score {top.score:.1f})\n")


def run(pkg_name: str, kb_path: str, model: str = "claude-haiku-4-5", build: bool = False, test: bool = False, local: bool = False, compiler: str = None, retrieval: bool = True):
    context = load_context(pkg_name, kb_path)
    schema = context.package_schema
    risk_deps, installed_compilers, all_compilers, failure_rate = analyze_deps(context)

    import spack.repo
    pkg_cls = spack.repo.PATH.get_pkg_class(schema.name)
    is_python = any(c.__name__ == "PythonPackage" for c in pkg_cls.__mro__)

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
    py_str = " | python package" if is_python else ""
    print(f"\n{schema.name} | KB: {len(context.kb_entries)} entries | {rate_str} | {compiler_str}{retrieval_str}{py_str}")

    if not installed_compilers:
        print("(hint: run 'spack compiler find' to register compilers)")

    print(f"Generating specs via {model}...")

    from ai_test.kb.store import load as load_full_kb
    all_kb = load_full_kb(kb_path)
    auto_patterns = mine_persistent_patterns(all_kb) if retrieval else []

    llm_result = call_llm(
        schema, risk_deps, compilers_for_plan, context.kb_entries, model,
        retrieval=retrieval, auto_patterns=auto_patterns,
    )

    if not llm_result.suggested_specs:
        print("LLM did not return parseable specs.")
        print(llm_result.raw)
        return


    results = execute_all(
        llm_result.suggested_specs,
        schema,
        kb_path,
        installed_compilers=installed_compilers,
        model=model,
        build=build,
        test=test,
    )

    ci = [r for r in results if not r.concretized and r.failure_reason is None]
    failed = [r for r in results if not r.concretized and r.failure_reason is not None]
    passed = [r for r in results if r.concretized]
    built = [r for r in results if r.installed]
    test_run = [r for r in results if r.test_passed is not None]

    parts = [f"{len(passed) + len(failed)} tested", f"{len(passed)} concretized", f"{len(failed)} failed"]
    if build or test:
        parts.append(f"{len(built)} built")
    if test_run:
        t_pass = sum(1 for r in test_run if r.test_passed)
        t_fail = sum(1 for r in test_run if not r.test_passed)
        parts.append(f"{t_pass} test_pass")
        if t_fail:
            parts.append(f"{t_fail} test_fail")
    if ci:
        ci_needed = [c for c in all_compilers if c not in installed_compilers]
        parts.append(f"{len(ci)} queued for CI ({', '.join(ci_needed)})")
    print(f"\n{' | '.join(parts)} : {kb_path}")

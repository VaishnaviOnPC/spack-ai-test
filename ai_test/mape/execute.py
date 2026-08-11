import os
import sys
import json
import re
from contextlib import contextmanager
from datetime import datetime

import spack.concretize
import spack.installer
import spack.spec
import spack.store
import spack.repo

from ai_test.extract.schema import PackageSchema
from ai_test.kb.schema import KBEntry
from ai_test.kb.store import append_entry, is_known, load as load_kb, replace_entry
from ai_test.mape.schema import CandidateSpec

_SKIP_VARIANT_NAMES = {"arch", "os", "target", "platform"}

_ENV_TOOLS = {
    "tar", "gmake", "make", "python", "python-venv", "re2c",
    "clingo-bootstrap", "bison", "perl", "m4", "autoconf",
    "automake", "libtool", "pkgconf", "util-macros",
}


@contextmanager
def suppress_clingo_warnings():
    sys.stderr.flush()
    devnull = os.open(os.devnull, os.O_WRONLY)
    old_stderr = os.dup(2)
    os.dup2(devnull, 2)
    try:
        yield
    finally:
        sys.stderr.flush()
        os.dup2(old_stderr, 2)
        os.close(old_stderr)
        os.close(devnull)


@contextmanager
def suppress_output():
    sys.stdout.flush()
    sys.stderr.flush()
    devnull = os.open(os.devnull, os.O_WRONLY)
    old_stdout = os.dup(1)
    old_stderr = os.dup(2)
    os.dup2(devnull, 1)
    os.dup2(devnull, 2)
    try:
        yield
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(old_stdout, 1)
        os.dup2(old_stderr, 2)
        os.close(old_stdout)
        os.close(old_stderr)
        os.close(devnull)


def run_spec(spec_str: str) -> tuple:
    try:
        with suppress_clingo_warnings():
            spack.concretize.concretize_one(spack.spec.Spec(spec_str))
        return True, None
    except (Exception, SystemExit) as e:
        return False, str(e)


def run_install(spec_str: str) -> tuple:
    try:
        with suppress_clingo_warnings():
            spec = spack.concretize.concretize_one(spack.spec.Spec(spec_str))
        installer = spack.installer.PackageInstaller(
            [spec.package],
            fail_fast=True,
            root_policy="source_only",
            dependencies_policy="source_only"
        )
        with suppress_output():
            installer.install()
        return True, None
    except (Exception, SystemExit) as e:
        return False, str(e)


def run_test(spec_str: str) -> tuple:
    installed = spack.store.STORE.db.query(spec_str)
    if not installed:
        return None, "not installed"

    spec = installed[0]
    pkg = spec.package

    test_methods = [
        name for name in dir(type(pkg))
        if name.startswith("test_") and callable(getattr(type(pkg), name, None))
    ]
    if not test_methods:
        return None, "no tests defined"

    try:
        import subprocess
        result = subprocess.run(
            ["spack", "test", "run", "--fail-fast", spec_str],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            output = result.stdout + "\n" + result.stderr
            lines = [l.strip() for l in output.splitlines() if l.strip()]
            error_lines = [
                l for l in lines 
                if ("fail" in l.lower() or "error" in l.lower()) and not l.startswith("=====")
            ]
            summary = error_lines[0] if error_lines else (lines[-1] if lines else "test suite failed")
            return False, summary
        return True, None
    except OSError as e:
        return False, f"failed to run spack tests: {e}"


def _error_type(error: str) -> str:
    e = error.lower()
    if "no such variant" in e or "unknown variant" in e or "invalid variant" in e:
        return "unknown_variant"
    if "cannot satisfy" in e or "conflicts with" in e:
        return "constraint_conflict"
    if "no version" in e or "version range" in e:
        return "version_error"
    if "deprecated" in e:
        return "deprecated"
    if "compiler" in e and ("not found" in e or "not installed" in e):
        return "compiler_not_found"
    return "unknown"


def _extract_failing_pkg(install_error: str) -> str:
    skip = {"the", "following", "packages", "failed"}
    for line in (install_error or "").splitlines():
        line = line.strip()
        m = re.match(r'^([a-zA-Z][a-zA-Z0-9\-]*)(@[^\s/]+)?', line)
        if m and m.group(1).lower() not in skip:
            return (m.group(1) + (m.group(2) or "")).rstrip(":")
    return "unknown"


def _classify_failure(pkg_name: str, install_error: str) -> str:
    for line in (install_error or "").splitlines():
        line = line.strip()
        m = re.match(r'^([a-zA-Z][a-zA-Z0-9\-]*)@', line)
        if m:
            failing = m.group(1).lower()
            if failing in _ENV_TOOLS:
                return "env_fail"
            if failing != pkg_name.lower():
                return "dep_fail"
            return "build_fail"
    return "build_fail"


def _reproduce(spec_str: str) -> bool:
    print("  [reproduce] re-running build to confirm failure...", flush=True)
    installed, _ = run_install(spec_str)
    if not installed:
        print("  [reproduce] confirmed: failure reproduces")
        return True
    print("  [reproduce] flaky: second build succeeded => skipping bisect")
    return False


def _spec_compiler(spec_str: str):
    m = re.search(r'%([A-Za-z0-9_\.-]+(@[\d\.]+)?)', spec_str)
    return m.group(1).lstrip("%=") if m else None


def _validate_spec(spec_str: str, schema: PackageSchema) -> list:
    issues = []
    root = spec_str.split('^')[0].split('%')[0]

    root_ver_m = re.match(r'^\S+@([\d][^\s+~^%]*)', root.strip())
    if root_ver_m:
        root_ver = root_ver_m.group(1)
        pkg_class = spack.repo.PATH.get_pkg_class(schema.name)
        known_root = {str(v) for v in getattr(pkg_class, 'versions', {}).keys()}
        if root_ver not in known_root:
            issues.append(
                f"root version '@{root_ver}' does not exist in Spack registry for {schema.name}"
            )

    tokens = root.split()[1:]

    for tok in tokens:
        m = re.match(r'^[+~](\w+)$', tok)
        if m:
            if m.group(1) not in schema.variants:
                issues.append(f"unknown variant '{m.group(1)}'")
            continue
        m = re.match(r'^(\w+)=(\S+)', tok)
        if m:
            name, value = m.group(1), m.group(2)
            if name in _SKIP_VARIANT_NAMES:
                continue
            if name not in schema.variants:
                issues.append(f"unknown variant '{name}'")
            elif schema.variants[name].values is not None:
                if value not in schema.variants[name].values:
                    issues.append(f"invalid value '{name}={value}' (declared: {schema.variants[name].values})")

    from ai_test.config import BUILD_TOOLS

    for dep_tok in re.finditer(r'\^([\w\-]+)(@[\d][^\s^%]*)?(%\S+)?', spec_str):
        dep_name = dep_tok.group(1)

        if dep_tok.group(3):
            issues.append(f"dep spec '^{dep_name}' has a compiler suffix '{dep_tok.group(3)}' which is not valid syntax")

        if dep_tok.group(2):
            if dep_name in BUILD_TOOLS:
                issues.append(f"invalid test axis: pinning build tool '^{dep_name}' is not allowed")
                continue

            ver_str = dep_tok.group(2).lstrip('@')
            try:
                pkg_class = spack.repo.PATH.get_pkg_class(dep_name)
                versions_dict = getattr(pkg_class, 'versions', {})
                known = {str(v) for v, args in versions_dict.items() if not args.get('deprecated', False)}
                if ver_str not in known:
                    issues.append(f"dep version '^{dep_name}@{ver_str}' does not exist or is deprecated in Spack registry")
            except spack.repo.UnknownPackageError:
                pass
    return issues


def _repair_spec(failed_spec, error, installed_compilers, model):
    from ai_test.llm.client import LLMClient
    from ai_test.llm.prompt import SYSTEM_PROMPT

    category = _error_type(error)
    if category in ("constraint_conflict", "unknown_variant"):
        return None

    compiler_list = ", ".join("%" + c for c in installed_compilers)
    err_summary = error.splitlines()[0]

    hints = {
        "version_error": "The version used does not exist. Pick a different valid version.",
        "deprecated": "The version used is deprecated. Use an older but non-deprecated version.",
        "compiler_not_found": f"Compiler not found. Use only: {compiler_list}.",
        "unknown": "",
    }

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"The spec '{failed_spec}' failed concretization:\n{err_summary}\n"
                f"{hints.get(category, '')}\n\n"
                f"Generate ONE corrected spec. Use only these compilers: {compiler_list}.\n"
                f"Output only: {{\"test_scenarios\": [\"<corrected spec>\"]}}"
            ),
        },
    ]

    raw = LLMClient(model=model).ask(messages)
    cleaned = re.sub(r"```json|```", "", raw).strip()
    try:
        data = json.loads(cleaned)
        scenarios = data.get("test_scenarios", [])
        return str(scenarios[0]) if scenarios else None
    except json.JSONDecodeError:
        return None


def execute_all(specs, schema: PackageSchema, kb_path: str, installed_compilers=None, model="claude-haiku-4-5", build=False, test=False, bisect=False):
    existing = load_kb(kb_path)
    results = []

    seen_this_run = set()

    for spec_str in specs:
        if spec_str in seen_this_run:
            print(f"[DUPLICATE] {spec_str}  (duplicate in this run, skipping)")
            continue
        seen_this_run.add(spec_str)

        if is_known(existing, schema.name, spec_str, schema.sha256):
            print(f"[KNOWN] {spec_str}  (already in KB, skipping)")
            results.append(CandidateSpec(spec_str=spec_str, concretized=True))
            continue

        issues = _validate_spec(spec_str, schema)
        if issues:
            print(f"[SKIP] {spec_str}  ({issues[0]})")
            continue

        compiler = _spec_compiler(spec_str)
        if compiler and installed_compilers is not None and compiler not in installed_compilers:
            print(f"[CI QUEUE] {spec_str} (CI queue: {compiler} not installed locally)")
            entry = KBEntry(
                pkg_name=schema.name,
                spec=spec_str,
                concretized=False,
                failure_reason=None,
                pkg_hash=schema.sha256,
                timestamp=datetime.now().isoformat(),
                validation_status="ci_queue",
            )
            append_entry(kb_path, entry)
            results.append(CandidateSpec(spec_str=spec_str, concretized=False))
            continue

        passed, error = run_spec(spec_str)
        repair_attempts = 0

        if not passed and installed_compilers:
            repaired = _repair_spec(spec_str, error, installed_compilers, model)
            if repaired and repaired != spec_str:
                repair_attempts = 1
                passed, error = run_spec(repaired)
                spec_str = repaired

        installed, install_error = False, None
        test_passed, test_error = None, None

        if passed and (build or test):
            print(f"[*] {spec_str} (installing...)")
            installed, install_error = run_install(spec_str)

        if installed and test:
            test_passed, test_error = run_test(spec_str)

        if test_passed is True:
            status = "TEST_PASS"
        elif test_passed is False:
            status = "TEST_FAIL"
        elif installed:
            status = "INSTALLED"
        elif build and passed:
            status = "BUILD_FAIL"
        elif passed:
            status = "PASS"
        else:
            status = "FAIL"

        print(f"[{status}] {spec_str}")
        if status == "BUILD_FAIL" and install_error:
            print(f"       {install_error.strip().splitlines()[0]}")
        if status == "TEST_FAIL" and test_error:
            print(f"       {test_error.strip().splitlines()[0]}")

        entry = KBEntry(
            pkg_name=schema.name,
            spec=spec_str,
            concretized=passed,
            failure_reason=error,
            pkg_hash=schema.sha256,
            timestamp=datetime.now().isoformat(),
            repair_attempts=repair_attempts,
            validation_status="validated",
            installed=installed,
            install_error=install_error,
            test_passed=test_passed,
            test_error=test_error,
        )
        append_entry(kb_path, entry)
        results.append(CandidateSpec(
            spec_str=spec_str,
            concretized=passed,
            failure_reason=error,
            installed=installed,
            install_error=install_error,
            test_passed=test_passed,
            test_error=test_error,
        ))

        if bisect and status == "TEST_FAIL":
            print(f"  TEST_FAIL: test suite failed in target package => bisecting")
            from ai_test.mape.bisect import auto_bisect_range
            auto_bisect_range(
                schema.name, spec_str,
                test=True,
                kb_path=kb_path,
            )
        elif bisect and status == "BUILD_FAIL":
            classification = _classify_failure(schema.name, install_error)
            if classification == "env_fail":
                failing = _extract_failing_pkg(install_error)
                print(f"  ENV_FAIL: '{failing}' is an environment tool => skipping bisect")
            elif classification == "dep_fail":
                failing = _extract_failing_pkg(install_error)
                print(f"  DEP_FAIL: dependency '{failing}' failed => skipping bisect")
            else:
                print(f"  BUILD_FAIL: failure is in target package")
                if _reproduce(spec_str):
                    from ai_test.mape.bisect import auto_bisect_range
                    auto_bisect_range(
                        schema.name, spec_str,
                        test=False,
                        kb_path=kb_path,
                    )

    return results

def execute_queued(
    pkg_name: str,
    kb_path: str,
    build: bool = False,
    test: bool = False,
    bisect: bool = False,
) -> list:
    from ai_test.extract import extract

    all_entries = load_kb(kb_path)
    pending = [
        e for e in all_entries
        if e.pkg_name == pkg_name and e.validation_status == "pending"
    ]

    if not pending:
        print(f"No pending specs found for '{pkg_name}' in {kb_path}")
        return []

    schema = extract(pkg_name)

    print(f"\n{pkg_name} | {len(pending)} pending specs | offline execution")
    if build or test:
        action = "build+test" if test else "build"
        print(f"Mode: concretize + {action}")
    else:
        print("Mode: concretize only")

    results = []
    for entry in pending:
        spec_str = entry.spec

        issues = _validate_spec(spec_str, schema)
        if issues:
            print(f"[SKIP] {spec_str}  ({issues[0]})")
            updated = KBEntry(
                pkg_name=entry.pkg_name,
                spec=spec_str,
                concretized=False,
                failure_reason=f"pre-validation: {issues[0]}",
                pkg_hash=entry.pkg_hash,
                timestamp=datetime.now().isoformat(),
                validation_status="validated",
            )
            replace_entry(kb_path, updated)
            results.append(CandidateSpec(
                spec_str=spec_str,
                concretized=False,
                failure_reason=updated.failure_reason,
            ))
            continue

        passed, error = run_spec(spec_str)

        installed, install_error = False, None
        test_passed, test_error = None, None

        if passed and (build or test):
            print(f"[*] {spec_str} (installing...)")
            installed, install_error = run_install(spec_str)

        if installed and test:
            test_passed, test_error = run_test(spec_str)

        if test_passed is True:
            status = "TEST_PASS"
        elif test_passed is False:
            status = "TEST_FAIL"
        elif installed:
            status = "INSTALLED"
        elif build and passed:
            status = "BUILD_FAIL"
        elif passed:
            status = "PASS"
        else:
            status = "FAIL"

        print(f"[{status}] {spec_str}")
        if status == "BUILD_FAIL" and install_error:
            print(f"       {install_error.strip().splitlines()[0]}")
        if status == "TEST_FAIL" and test_error:
            print(f"       {test_error.strip().splitlines()[0]}")

        updated = KBEntry(
            pkg_name=entry.pkg_name,
            spec=spec_str,
            concretized=passed,
            failure_reason=error,
            pkg_hash=entry.pkg_hash,
            timestamp=datetime.now().isoformat(),
            repair_attempts=entry.repair_attempts,
            validation_status="validated",
            installed=installed,
            install_error=install_error,
            test_passed=test_passed,
            test_error=test_error,
        )
        replace_entry(kb_path, updated)
        results.append(CandidateSpec(
            spec_str=spec_str,
            concretized=passed,
            failure_reason=error,
            installed=installed,
            install_error=install_error,
            test_passed=test_passed,
            test_error=test_error,
        ))

        if bisect and status == "TEST_FAIL":
            print(f"  TEST_FAIL: test suite failed in target package => bisecting")
            from ai_test.mape.bisect import auto_bisect_range
            auto_bisect_range(
                entry.pkg_name, spec_str,
                test=True,
                kb_path=kb_path,
            )
        elif bisect and status == "BUILD_FAIL":
            classification = _classify_failure(entry.pkg_name, install_error)
            if classification == "env_fail":
                failing = _extract_failing_pkg(install_error)
                print(f"  ENV_FAIL: '{failing}' is an environment tool => skipping bisect")
            elif classification == "dep_fail":
                failing = _extract_failing_pkg(install_error)
                print(f"  DEP_FAIL: dependency '{failing}' failed => skipping bisect")
            else:
                print(f"  BUILD_FAIL: failure is in target package")
                if _reproduce(spec_str):
                    from ai_test.mape.bisect import auto_bisect_range
                    auto_bisect_range(
                        entry.pkg_name, spec_str,
                        test=False,
                        kb_path=kb_path,
                    )

    failed = [r for r in results if not r.concretized]
    passed_r = [r for r in results if r.concretized]
    built = [r for r in results if r.installed]
    test_run = [r for r in results if r.test_passed is not None]
    parts = [f"{len(results)} processed", f"{len(passed_r)} concretized", f"{len(failed)} failed"]
    if build or test:
        parts.append(f"{len(built)} built")
    if test_run:
        t_pass = sum(1 for r in test_run if r.test_passed)
        t_fail = sum(1 for r in test_run if not r.test_passed)
        parts.append(f"{t_pass} test_pass")
        if t_fail:
            parts.append(f"{t_fail} test_fail")
    print(f"\n{' | '.join(parts)} : {kb_path}")

    return results

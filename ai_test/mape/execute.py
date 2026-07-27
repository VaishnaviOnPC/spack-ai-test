import os
import sys
import json
import re
from contextlib import contextmanager
from datetime import datetime

import spack.concretize
import spack.installer
import spack.spec

from ai_test.extract.schema import PackageSchema
from ai_test.kb.schema import KBEntry
from ai_test.kb.store import append_entry, is_known, load as load_kb
from ai_test.mape.schema import CandidateSpec


@contextmanager
def suppress_clingo_warnings():
    sys.stderr.flush()
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        old_stderr = os.dup(2)
        os.dup2(devnull, 2)
    except Exception:
        yield
        return
    try:
        yield
    finally:
        sys.stderr.flush()
        os.dup2(old_stderr, 2)
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
        installer.install()
        return True, None
    except (Exception, SystemExit) as e:
        return False, str(e)


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


def _spec_compiler(spec_str: str):
    m = re.search(r'%([A-Za-z0-9_\.-]+(@[\d\.]+)?)', spec_str)
    return m.group(1).lstrip("%=") if m else None


def _validate_spec(spec_str: str, schema: PackageSchema) -> list:
    issues = []
    _SKIP_NAMES = {"arch", "os", "target", "platform"}

    root = spec_str.split('^')[0].split('%')[0]
    tokens = root.split()[1:]

    for tok in tokens:
        m = re.match(r'^[+~](\w+)$', tok)
        if m:
            name = m.group(1)
            if name not in schema.variants:
                issues.append(f"unknown variant '{name}'")
            continue
        m = re.match(r'^(\w+)=(\S+)', tok)
        if m:
            name, value = m.group(1), m.group(2)
            if name in _SKIP_NAMES:
                continue
            if name not in schema.variants:
                issues.append(f"unknown variant '{name}'")
            elif schema.variants[name].values is not None:
                if value not in schema.variants[name].values:
                    issues.append(f"invalid value '{name}={value}' (declared: {schema.variants[name].values})")

    import spack.repo
    for dep_tok in re.finditer(r'\^([\w\-]+)(@[\d][^\s^%]*)?(%\S+)?', spec_str):
        dep_name = dep_tok.group(1)

        if dep_tok.group(3):
            issues.append(f"dep spec '^{dep_name}' has a compiler suffix '{dep_tok.group(3)}' which is not valid syntax")

        if dep_tok.group(2):
            ver_str = dep_tok.group(2).lstrip('@')
            try:
                pkg_class = spack.repo.PATH.get_pkg_class(dep_name)
                known = {str(v) for v in getattr(pkg_class, 'versions', {}).keys()}
                if ver_str not in known:
                    issues.append(f"dep version '^{dep_name}@{ver_str}' does not exist in Spack registry")
            except Exception:
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

    client = LLMClient(model=model)
    raw = client.ask(messages)
    cleaned = re.sub(r"```json|```", "", raw).strip()
    try:
        data = json.loads(cleaned)
        scenarios = data.get("test_scenarios", [])
        return str(scenarios[0]) if scenarios else None
    except json.JSONDecodeError:
        return None


def execute_all(specs, schema: PackageSchema, kb_path: str, installed_compilers=None, model="claude-haiku-4-5", build=False):
    existing = load_kb(kb_path)
    results = []

    for spec_str in specs:
        if is_known(existing, schema.name, spec_str, schema.sha256):
            print(f"[~] {spec_str}  (already in KB, skipping)")
            results.append(CandidateSpec(spec_str=spec_str, concretized=True))
            continue

        issues = _validate_spec(spec_str, schema)
        if issues:
            print(f"[SKIP] {spec_str}  ({issues[0]})")
            continue

        compiler = _spec_compiler(spec_str)
        if compiler and installed_compilers is not None and compiler not in installed_compilers:
            print(f"[>] {spec_str} (CI queue: {compiler} not installed locally)")
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
        if passed and build:
            print(f"[*] {spec_str} (installing...)")
            installed, install_error = run_install(spec_str)

        if build and passed:
            status = "INSTALLED" if installed else "BUILD_FAIL"
        else:
            status = "PASS" if passed else "FAIL"

        print(f"[{status}] {spec_str}")
        if status == "BUILD_FAIL" and install_error:
            # Print just the first line of the install error to avoid clutter
            err_line = install_error.strip().split("\n")[0]
            print(f"       -> {err_line}")

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
        )
        append_entry(kb_path, entry)
        results.append(CandidateSpec(
            spec_str=spec_str,
            concretized=passed,
            failure_reason=error,
            installed=installed,
            install_error=install_error,
        ))

    return results

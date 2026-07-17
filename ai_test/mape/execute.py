import json
import re
from datetime import datetime

import spack.concretize
import spack.installer
import spack.spec

from ai_test.extract.schema import PackageSchema
from ai_test.kb.schema import KBEntry
from ai_test.kb.store import append_entry, is_known, load as load_kb
from ai_test.mape.schema import CandidateSpec


def run_spec(spec_str: str) -> tuple:
    try:
        spack.concretize.concretize_one(spack.spec.Spec(spec_str))
        return True, None
    except (Exception, SystemExit) as e:
        return False, str(e)


def run_install(spec_str: str) -> tuple:
    try:
        spec = spack.concretize.concretize_one(spack.spec.Spec(spec_str))
        installer = spack.installer.PackageInstaller([spec.package])
        installer.install(fail_fast=True, no_cache=True)
        return True, None
    except (Exception, SystemExit) as e:
        return False, str(e)


def _error_type(error: str) -> str:
    e = error.lower()
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


def _repair_spec(failed_spec, error, installed_compilers, model):
    from ai_test.llm.client import LLMClient
    from ai_test.llm.prompt import SYSTEM_PROMPT

    category = _error_type(error)
    if category == "constraint_conflict":
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

        status = "INSTALLED" if installed else ("PASS" if passed else "FAIL")
        print(f"[{status}] {spec_str}")
        if error or install_error:
            print(f"{(install_error or error).splitlines()[0]}")

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

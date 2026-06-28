import json
import re
import subprocess
from datetime import datetime
from typing import List

from ai_test.extract.schema import PackageSchema
from ai_test.kb.schema import KBEntry
from ai_test.kb.store import append_entry, is_known, load as load_kb
from ai_test.mape.schema import CandidateSpec


def run_spec(spec_str: str) -> tuple:
    result = subprocess.run(
        f"spack spec \"{spec_str}\"",
        shell=True,
        capture_output=True,
        text=True,
    )
    passed = result.returncode == 0
    error = result.stderr.strip() if not passed else None
    return passed, error


def _spec_compiler(spec_str: str):
    m = re.search(r'%(\w+@[\d.]+)', spec_str)
    return m.group(1) if m else None


def _repair_spec(failed_spec: str, error: str, installed_compilers: List[str], model: str):
    from ai_test.llm.client import LLMClient
    from ai_test.llm.prompt import SYSTEM_PROMPT

    compiler_list = ", ".join("%" + c for c in installed_compilers)
    err_summary = error.splitlines()[0]

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"The spec '{failed_spec}' failed concretization:\n{err_summary}\n\n"
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


def execute_all(
    specs: List[str],
    schema: PackageSchema,
    kb_path: str,
    installed_compilers: List[str] = None,
    model: str = "claude-sonnet-4-6",
) -> List[CandidateSpec]:
    existing = load_kb(kb_path)
    results = []

    for spec_str in specs:
        if is_known(existing, schema.name, spec_str, schema.sha256):
            print(f"  [~] {spec_str}  (already in KB, skipping)")
            results.append(CandidateSpec(spec_str=spec_str, concretized=True, failure_reason=None))
            continue

        compiler = _spec_compiler(spec_str)
        is_installed = not installed_compilers or compiler in installed_compilers

        if not is_installed:
            print(f"  [→] {spec_str}  (CI queue: {compiler} not installed locally)")
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
            results.append(CandidateSpec(spec_str=spec_str, concretized=False, failure_reason=None))
            continue

        passed, error = run_spec(spec_str)
        repair_attempts = 0

        if not passed and installed_compilers:
            repaired = _repair_spec(spec_str, error, installed_compilers, model)
            if repaired and repaired != spec_str:
                repair_attempts = 1
                passed, error = run_spec(repaired)
                spec_str = repaired

        entry = KBEntry(
            pkg_name=schema.name,
            spec=spec_str,
            concretized=passed,
            failure_reason=error,
            pkg_hash=schema.sha256,
            timestamp=datetime.now().isoformat(),
            repair_attempts=repair_attempts,
            validation_status="validated",
        )
        append_entry(kb_path, entry)
        results.append(CandidateSpec(spec_str=spec_str, concretized=passed, failure_reason=error))

    return results

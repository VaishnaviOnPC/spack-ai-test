import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import spack.repo
import spack.version

PASS = "pass"
CONCRETIZE_FAIL = "concretize_fail"
BUILD_FAIL = "build_fail"
TEST_FAIL = "test_fail"


@dataclass
class BisectResult:
    pkg_name: str
    failed_spec: str
    first_bad: Optional[str] = None
    first_bad_type: Optional[str] = None
    last_good_before: Optional[str] = None
    last_bad: Optional[str] = None
    last_bad_type: Optional[str] = None
    first_fixed: Optional[str] = None
    concretize_boundary_before: Optional[str] = None
    concretize_boundary_after: Optional[str] = None
    steps: List[Tuple[str, str]] = field(default_factory=list)
    kb_hits: int = 0


def _extract_version(spec_str: str) -> Optional[str]:
    m = re.search(r"^[^\@\s]+@([^\s%^+~=]+)", spec_str.strip())
    return m.group(1) if m else None


def _replace_version(spec_str: str, new_version: str) -> str:
    spec_str = spec_str.strip()
    if re.search(r"^[^\@\s]+@([^\s%^+~=]+)", spec_str):
        return re.sub(r"^([^\@\s]+)@([^\s%^+~=]+)", rf"\1@{new_version}", spec_str)
    m = re.match(r"^([^\s%^+~=]+)(.*)", spec_str)
    if m:
        return f"{m.group(1)}@{new_version}{m.group(2)}"
    return spec_str


def _all_versions(pkg_name: str) -> List[str]:
    try:
        pkg_cls = spack.repo.PATH.get_pkg_class(pkg_name)
    except spack.repo.UnknownPackageError:
        return []
    versions = []
    for v, attrs in getattr(pkg_cls, "versions", {}).items():
        if not attrs.get("deprecated", False):
            versions.append(spack.version.Version(str(v)))
    return [str(v) for v in sorted(versions)]


def _kb_lookup(spec_str: str, kb_path: Optional[str], pkg_name: str, pkg_hash: str) -> Optional[str]:
    if not kb_path or not pkg_hash:
        return None
        for e in load_kb(kb_path):
            if (e.pkg_name == pkg_name
                    and e.spec == spec_str
                    and e.pkg_hash == pkg_hash
                    and e.validation_status == "validated"):
                if e.installed:
                    return PASS
                if not e.concretized:
                    return CONCRETIZE_FAIL
                if e.install_error:
                    return BUILD_FAIL
                if e.test_passed is False:
                    return TEST_FAIL
    return None


def _outcome(
    spec_str: str,
    test: bool,
    kb_path: Optional[str],
    pkg_name: str,
    pkg_hash: str,
    result: BisectResult,
) -> str:
    cached = _kb_lookup(spec_str, kb_path, pkg_name, pkg_hash)
    if cached is not None:
        result.kb_hits += 1
        return cached

    from ai_test.mape.execute import run_spec, run_install, run_test

    ok, _ = run_spec(spec_str)
    if not ok:
        return CONCRETIZE_FAIL

    installed, _ = run_install(spec_str)
    if not installed:
        return BUILD_FAIL

    if test:
        passed, _ = run_test(spec_str)
        return PASS if passed else TEST_FAIL

    return PASS


def _print_step(kind: str, step: int, spec: str, outcome: Optional[str] = None):
    label = f"[{kind} step={step}]"
    if outcome is None:
        print(f"     {label} {spec}  (evaluating)", end="", flush=True)
    else:
        print(f"\r     {label} {spec}  => {outcome.upper().replace('_', ' ')}       ")


def _jump(
    versions: List[str],
    start_idx: int,
    direction: int,
    failed_spec: str,
    test: bool,
    kb_path: Optional[str],
    pkg_name: str,
    pkg_hash: str,
    result: BisectResult,
) -> Tuple[Optional[int], Optional[int], Optional[str]]:
    step = 1
    prev_idx = start_idx
    concretize_boundary = None

    while True:
        curr_idx = start_idx + direction * step
        curr_idx = max(0, min(curr_idx, len(versions) - 1))

        spec = _replace_version(failed_spec, versions[curr_idx])
        _print_step("jump", step, spec)
        outcome = _outcome(spec, test, kb_path, pkg_name, pkg_hash, result)
        result.steps.append((spec, outcome))
        _print_step("jump", step, spec, outcome)

        if outcome == PASS:
            if direction == -1:
                return (curr_idx, prev_idx, None)
            else:
                return (prev_idx, curr_idx, None)

        if outcome == CONCRETIZE_FAIL:
            concretize_boundary = curr_idx
            if direction == -1:
                return (curr_idx, prev_idx, concretize_boundary)
            else:
                return (prev_idx, curr_idx, concretize_boundary)

        at_edge = (curr_idx == 0 and direction == -1) or (curr_idx == len(versions) - 1 and direction == +1)
        if at_edge:
            break

        prev_idx = curr_idx
        step *= 2

    return (None, None, None)


def _binary_search(
    versions: List[str],
    outer_idx: int,
    inner_idx: int,
    is_backward: bool,
    failed_spec: str,
    test: bool,
    kb_path: Optional[str],
    pkg_name: str,
    pkg_hash: str,
    result: BisectResult,
    seeking_pass: bool = True,
) -> Tuple[int, int, str, str]:
    lo, hi = (outer_idx, inner_idx) if outer_idx < inner_idx else (inner_idx, outer_idx)
    last_outcomes: Dict[int, str] = {}
    step = 0

    while hi - lo > 1:
        step += 1
        mid = (lo + hi) // 2
        spec = _replace_version(failed_spec, versions[mid])
        _print_step("bisect", step, spec)
        outcome = _outcome(spec, test, kb_path, pkg_name, pkg_hash, result)
        result.steps.append((spec, outcome))
        _print_step("bisect", step, spec, outcome)
        last_outcomes[mid] = outcome

        target = PASS if seeking_pass else CONCRETIZE_FAIL
        if (outcome == target) == is_backward:
            lo = mid
        else:
            hi = mid

    lo_outcome = last_outcomes.get(lo, PASS if seeking_pass and lo == outer_idx else BUILD_FAIL)
    hi_outcome = last_outcomes.get(hi, BUILD_FAIL if seeking_pass and hi == inner_idx else CONCRETIZE_FAIL)
    return lo, hi, lo_outcome, hi_outcome


def auto_bisect_range(
    pkg_name: str,
    failed_spec: str,
    test: bool = False,
    kb_path: Optional[str] = None,
) -> BisectResult:
    result = BisectResult(pkg_name=pkg_name, failed_spec=failed_spec)

    failed_ver = _extract_version(failed_spec)
    if not failed_ver:
        print("  [bisect] Cannot parse version from spec - aborting.")
        return result

    all_vers = _all_versions(pkg_name)
    if not all_vers:
        print("  [bisect] No versions found in Spack registry - aborting.")
        return result

    try:
        fail_idx = all_vers.index(failed_ver)
    except ValueError:
        fv = spack.version.Version(failed_ver)
        fail_idx = sum(1 for v in all_vers if spack.version.Version(v) < fv)
        fail_idx = min(fail_idx, len(all_vers) - 1)

    pkg_hash = ""
    from ai_test.extract import extract
    schema = extract(pkg_name)
    pkg_hash = schema.sha256

    print(f"\n  [bisect] analyzing {pkg_name} failure range ({len(all_vers)} versions)")

    if fail_idx > 0:
        print(f"  [bisect] searching backward...")
        outer_idx, inner_idx, concretize_bdry = _jump(
            all_vers, fail_idx, -1, failed_spec, test, kb_path, pkg_name, pkg_hash, result
        )

        if outer_idx is not None:
            seeking = concretize_bdry is None
            lo, hi, lo_out, hi_out = _binary_search(
                all_vers, outer_idx, inner_idx,
                is_backward=True, failed_spec=failed_spec, test=test,
                kb_path=kb_path, pkg_name=pkg_name, pkg_hash=pkg_hash, result=result,
                seeking_pass=seeking,
            )

            if seeking:
                result.last_good_before = _replace_version(failed_spec, all_vers[lo])
                result.first_bad = _replace_version(failed_spec, all_vers[hi])
                result.first_bad_type = hi_out
            else:
                result.first_bad = _replace_version(failed_spec, all_vers[lo])
                result.first_bad_type = lo_out
                result.concretize_boundary_before = _replace_version(failed_spec, all_vers[hi])
        else:
            print("  [bisect] all older versions also fail")
    else:
        print("  [bisect] failing version is the oldest known")

    if fail_idx < len(all_vers) - 1:
        print(f"  [bisect] searching forward...")
        inner_idx2, outer_idx2, concretize_bdry2 = _jump(
            all_vers, fail_idx, +1, failed_spec, test, kb_path, pkg_name, pkg_hash, result
        )

        if outer_idx2 is not None:
            seeking2 = concretize_bdry2 is None
            lo2, hi2, lo_out2, hi_out2 = _binary_search(
                all_vers, outer_idx2, inner_idx2,
                is_backward=False, failed_spec=failed_spec, test=test,
                kb_path=kb_path, pkg_name=pkg_name, pkg_hash=pkg_hash, result=result,
                seeking_pass=seeking2,
            )

            if seeking2:
                result.last_bad = _replace_version(failed_spec, all_vers[lo2])
                result.last_bad_type = lo_out2
                result.first_fixed = _replace_version(failed_spec, all_vers[hi2])
            else:
                result.last_bad = _replace_version(failed_spec, all_vers[lo2])
                result.last_bad_type = lo_out2
                result.concretize_boundary_after = _replace_version(failed_spec, all_vers[hi2])
        else:
            print("  [bisect] all newer versions also fail")
    else:
        print("  [bisect] failing version is the newest known")

    total_builds = len(result.steps)
    max_naive = fail_idx + (len(all_vers) - 1 - fail_idx)
    print(f"\n  [bisect] Total builds: {total_builds}  |  KB cache hits: {result.kb_hits}  |  Max naive: {max_naive}")

    fb_ver = _extract_version(result.first_bad) if result.first_bad else None
    lb_ver = _extract_version(result.last_bad) if result.last_bad else None
    cb_before = _extract_version(result.concretize_boundary_before) if result.concretize_boundary_before else None
    cb_after  = _extract_version(result.concretize_boundary_after)  if result.concretize_boundary_after  else None

    if fb_ver and lb_ver:
        print(f"  [bisect] Build failure range: {fb_ver} to {lb_ver}")
    elif fb_ver:
        print(f"  [bisect] Build failure range: {fb_ver} => (newest tested)  [{result.first_bad_type}]")
    elif lb_ver:
        print(f"  [bisect] Build failure range: (oldest tested) => {lb_ver}  [{result.last_bad_type}]")

    if result.last_good_before:
        print(f"  [bisect] Last known good: {_extract_version(result.last_good_before)}")
    if result.first_fixed:
        print(f"  [bisect] First fixed:     {_extract_version(result.first_fixed)}")

    if cb_before:
        print(f"  [bisect] Concretization boundary: {cb_before} => CONCRETIZE_FAIL (older versions incompatible with this spec)")
    if cb_after:
        print(f"  [bisect] Concretization boundary: {cb_after} => CONCRETIZE_FAIL (newer versions incompatible with this spec)")

    if kb_path and pkg_hash:
        from ai_test.kb.schema import KBEntry
        from ai_test.kb.store import replace_entry

        to_save = []
        if result.first_bad and result.first_bad_type != CONCRETIZE_FAIL:
            to_save.append((result.first_bad, False, f"bisect: first-bad boundary [{result.first_bad_type}]"))
        if result.last_good_before:
            to_save.append((result.last_good_before, True, "bisect: last-good-before boundary"))
        if result.first_fixed:
            to_save.append((result.first_fixed, True, "bisect: first-fixed boundary"))
        if result.last_bad and result.last_bad_type != CONCRETIZE_FAIL:
            to_save.append((result.last_bad, False, f"bisect: last-bad boundary [{result.last_bad_type}]"))

        for spec, is_good, note in to_save:
            entry = KBEntry(
                pkg_name=pkg_name,
                spec=spec,
                concretized=True,
                failure_reason=None if is_good else note,
                pkg_hash=pkg_hash,
                timestamp=datetime.now().isoformat(),
                validation_status="validated",
                installed=is_good,
                install_error=None if is_good else note,
            )
            replace_entry(kb_path, entry)

        if to_save:
            print(f"  [bisect] {len(to_save)} boundaries saved to KB: {kb_path}")

    return result

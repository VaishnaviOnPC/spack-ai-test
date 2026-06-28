SYSTEM_PROMPT = """\
You are a Spack HPC package manager expert.

Generate off-leading-edge test scenarios: Spack specs that CI does NOT test.
CI focuses on the newest versions with newest dependencies, target everything else:
- Older versions combined with newer compilers
- Version boundaries where upper limits may be missing
- Non-default variant combinations
- Compiler/ABI boundary crossings

Only use variants and versions explicitly declared in the package schema.
JSON output only, no prose, no markdown.\
"""

def _task_prompt(compilers=None) -> str:
    if compilers:
        compiler_constraint = f"Every spec MUST use one of these compilers: {', '.join('%' + c for c in compilers)}"
        example_compiler = "%" + compilers[0]
    else:
        compiler_constraint = "Every spec MUST include a compiler (e.g. %gcc@13.3.0)"
        example_compiler = "%gcc@13.3.0"

    return f"""\
Generate 3-5 Spack specs for off-leading-edge configurations not covered by CI.

Requirements:
- {compiler_constraint}
- Use +/~ for boolean variants (NOT variant=True or variant=False)
- Focus on older package versions, or non-default variant combinations

Output only:
{{"test_scenarios": ["<pkg@version +var ~var {example_compiler}>", ...]}}"""


def build_messages(pkg_ctx, risk_ctx, ref_ctx, conflict_ctx, compilers=None) -> list:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": pkg_ctx},
        {"role": "user", "content": risk_ctx},
        {"role": "user", "content": ref_ctx},
        {"role": "user", "content": conflict_ctx},
        {"role": "user", "content": _task_prompt(compilers)},
    ]


def repair_message(spec: str, error: str) -> dict:
    return {
        "role": "user",
        "content": f"Spec '{spec}' failed: {error}\nGenerate a corrected spec. JSON only.",
    }

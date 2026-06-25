SYSTEM_PROMPT = """\
You are a Spack HPC package manager expert.

Generate off-leading-edge test scenarios: Spack specs that CI does NOT test.
CI focuses on the newest versions with newest dependencies — target everything else:
- Older versions combined with newer compilers
- Version boundaries where upper limits may be missing
- Non-default variant combinations
- Compiler/ABI boundary crossings

Only use variants and versions explicitly declared in the package schema.
JSON output only, no prose, no markdown.\
"""

TASK_PROMPT = """\
Generate 3-5 Spack specs for off-leading-edge configurations not covered by CI.

Requirements:
- Every spec MUST include a compiler: %gcc@11.4.0, %gcc@12.3.0, %gcc@13.3.0, %clang@14.0.0, %clang@15.0.7, etc. Use compilers declared in the schema, prioritizing older versions. But avoid compilers with many declared conflicts unless necessary to create an off-leading-edge scenario. Do not use compilers that are known to be completely unsupported.
- Use +/~ for boolean variants (NOT variant=True or variant=False)
- Focus on older package versions, or non-default variant combinations

Output only:
{"test_scenarios": ["<pkg@version +var ~var %compiler@version>", ...]}\
"""


def build_messages(
    package_context: str,
    risk_context: str,
    reference_context: str,
    conflict_context: str,
) -> list:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": package_context},
        {"role": "user", "content": risk_context},
        {"role": "user", "content": reference_context},
        {"role": "user", "content": conflict_context},
        {"role": "user", "content": TASK_PROMPT},
    ]


def repair_message(spec: str, error: str) -> dict:
    return {
        "role": "user",
        "content": f"Spec '{spec}' failed: {error}\nGenerate a corrected spec. JSON only.",
    }

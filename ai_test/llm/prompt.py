SYSTEM_PROMPT = """\
You are a Spack HPC package manager expert.

Generate off-leading-edge test scenarios: Spack specs that CI does NOT test.
CI focuses on the newest versions with newest dependencies, target everything else:

- Always pin an older package version using exact @X.Y.Z syntax, never the latest
- Use non-default variant combinations 
- In at least one spec, pin key dependencies to their oldest compatible version using ^dep@X.Y.Z to check that the package's declared minimum requirements are actually correct
- Use your knowledge of each dependency's oldest stable release for realistic floor versions
- Cross compiler, ABI or major compiler version boundaries
- Only use variants and versions explicitly declared in the package schema
- JSON output only, no prose, no markdown\
"""

def task_prompt(compilers=None) -> str:
    if compilers:
        compiler_constraint = f"Every spec MUST use one of these compilers: {', '.join('%' + c for c in compilers)}"
        example_compiler = "%" + compilers[0]
    else:
        compiler_constraint = "Every spec MUST include a compiler (e.g. %gcc@13.3.0)"
        example_compiler = "%gcc@13.3.0"

    return f"""\
Generate 3-5 Spack specs that CI does not cover.

Requirements:
- {compiler_constraint}
- Use +/~ for boolean variants (NOT variant=True or variant=False)
- Focus on older package versions, or non-default variant combinations
- Flip at least one non-default variant per spec (e.g. ~shared, ~pic, +debug)
- In at least one spec, use ^dep@X.Y.Z to pin dependencies at their oldest compatible release

Output only:
{{"test_scenarios": ["<pkg@version +var ~var ^dep@version {example_compiler}>", ...]}}"""


def build_messages(pkg_ctx, risk_ctx, conflict_ctx, compilers=None) -> list:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": pkg_ctx},
        {"role": "user", "content": risk_ctx},
        {"role": "user", "content": conflict_ctx},
        {"role": "user", "content": task_prompt(compilers)},
    ]

SYSTEM_PROMPT = """\
You are a Spack HPC package manager expert. Your job is to find BUILD and TEST failures \
that Spack's CI pipeline misses — not concretization failures.

Spack's concretizer already enforces version constraints and conflicts perfectly. \
A spec that fails to concretize is NOT a useful result. \
Your goal is to generate specs that WILL concretize, but that CI does not build or test, \
because they use older versions, non-default variants, or unusual dependency combinations \
that might reveal compilation errors or functional regressions.

Rules:
- Every generated spec MUST be concretizable (satisfies all declared version constraints and conflicts)
- Use older but VALID package versions (not the latest, not non-existent versions)
- Use non-default variant combinations, one axis at a time, that change real build behavior
- Only use variants, versions, and dependency names that are explicitly declared in the package schema
- If a variant has allowed [values: ...], you MUST pick one of those exact values
- For any ^dep@version pin, use ONLY the exact version strings from the provided registry list
- Do NOT pin build infrastructure (py-pip, py-setuptools, cmake, ninja, etc.)
- Do NOT generate combinations that the package's declared conflicts() would reject
- Do NOT generate specs already in the knowledge base

ABI and linkage axes to explore (when declared in the schema):
- +shared / ~shared: changes linker behavior and ABI; flip from the default in one spec
- cxxstd: different C++ standards (11, 14, 17, 20) cause ABI incompatibilities

Python package axes:
- Pin python to different minor versions using ONLY versions from the provided registry list
- Test with non-default python-related variants if declared

- JSON output only, no prose, no markdown\
"""


def get_system_prompt(auto_patterns: list = None) -> str:
    if not auto_patterns:
        return SYSTEM_PROMPT
    discovered = "\n".join(f"- {p}" for p in auto_patterns)
    return (
        SYSTEM_PROMPT
        + "\n\nPatterns discovered from historical test data:\n"
        + discovered
    )


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
- Vary ONE major axis per spec: either (a) an older package version, or (b) a flipped variant, or (c) a pinned old dependency — not all three at once
- If a 'shared' variant exists: flip it from the default in at least one spec
- If a 'cxxstd' variant exists: try a non-default C++ standard value in at least one spec
- For any ^dep@version pin, use ONLY the exact version strings from the provided "Valid Spack registry versions" list; if no list is provided, do not pin any dependency version

Output only:
{{"test_scenarios": ["<pkg@version +var ~var ^dep@version {example_compiler}>", ...]}}"""


def build_messages(pkg_ctx, risk_ctx, conflict_ctx, compilers=None) -> list:
    return [
        {"role": "system", "content": get_system_prompt()},
        {"role": "user", "content": pkg_ctx},
        {"role": "user", "content": risk_ctx},
        {"role": "user", "content": conflict_ctx},
        {"role": "user", "content": task_prompt(compilers)},
    ]

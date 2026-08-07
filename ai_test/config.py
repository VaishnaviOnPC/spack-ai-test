import os
import spack.paths

_CONFIG_FILE = os.path.join(spack.paths.user_config_path, "ai_test.yaml")

_DEFAULTS = {
    "model": "claude-haiku-4-5",
    "kb": os.path.join(spack.paths.user_cache_path, "ai_test", "kb.json"),
    "ci_compilers": [
        "gcc@11.4.0",
        "gcc@12.3.0",
        "clang@14.0.0",
        "clang@15.0.7",
        "intel@2024.0.0",
    ],
}

BUILD_TOOLS = frozenset({
    "py-pip", "py-setuptools", "py-wheel", "py-cython", "py-flit-core",
    "py-meson-python", "py-hatchling", "py-poetry-core",
    "ninja", "pkgconfig", "cmake", "autoconf", "automake", "libtool",
})

_ENV = {
    "SPACK_AI_TEST_MODEL": "model",
    "SPACK_AI_TEST_KB": "kb",
}

_cache = None


def get() -> dict:
    global _cache
    if _cache is not None:
        return _cache

    cfg = dict(_DEFAULTS)

    if os.path.exists(_CONFIG_FILE):
        import yaml
        with open(_CONFIG_FILE) as f:
            file_data = yaml.safe_load(f) or {}
        cfg.update(file_data.get("ai_test", {}))

    for env_var, key in _ENV.items():
        val = os.environ.get(env_var)
        if val:
            cfg[key] = val

    _cache = cfg
    return _cache

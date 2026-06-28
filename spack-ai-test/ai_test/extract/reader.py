from typing import Dict, List
import spack.repo
from ai_test.extract.schema import DependencyInfo, VariantInfo


def get_pkg_class(pkg_name: str):
    return spack.repo.PATH.get_pkg_class(pkg_name)


def _dep_bound(dep_obj) -> str:
    if isinstance(dep_obj, dict):
        return dep_obj.get("versions", ":") or ":"
    versions = getattr(dep_obj, "versions", None)
    if versions is None:
        spec = getattr(dep_obj, "spec", None)
        if spec:
            versions = getattr(spec, "versions", None)
    if versions is not None:
        s = str(versions).lstrip("@")
        if s and s != ":":
            return s
    return ":"


def _dep_type(dep_obj) -> List[str]:
    if isinstance(dep_obj, dict):
        dt = dep_obj.get("type", None)
    else:
        dt = getattr(dep_obj, "type", None)
    if dt is None:
        return ["build", "link"]
    if isinstance(dt, (list, tuple, set, frozenset)):
        return sorted(str(t) for t in dt)
    return [str(dt)]


def extract_versions(pkg_class) -> List[str]:
    def ver_key(v: str):
        parts = []
        for tok in v.replace("-", ".").split("."):
            if tok.isdigit():
                parts.append((0, int(tok)))
            else:
                parts.append((1, tok))
        return parts

    raw = [
        str(v) for v, attrs in getattr(pkg_class, "versions", {}).items()
        if not attrs.get("deprecated", False)
    ]
    return sorted((str(v) for v in raw), key=ver_key, reverse=True)


def extract_dependencies(pkg_class) -> List[DependencyInfo]:
    deps = []
    for when_spec, dep_dict in getattr(pkg_class, "dependencies", {}).items():
        when = str(when_spec).strip() or None
        if not isinstance(dep_dict, dict):
            continue
        for dep_name, dep_obj in dep_dict.items():
            deps.append(DependencyInfo(
                name=str(dep_name),
                bound=_dep_bound(dep_obj),
                dep_type=_dep_type(dep_obj),
                when=when,
            ))
    return deps


def extract_conflicts(pkg_class) -> List[Dict[str, str]]:
    result = []
    for conflict_key, conditions in getattr(pkg_class, "conflicts", {}).items():
        spec = str(conflict_key)
        for item in conditions:
            when = str(item[0] if isinstance(item, (list, tuple)) else item).strip() or "always"
            result.append({spec: when})
    return result


def _parse_variant(vdef, pkg_when):
    if isinstance(vdef, dict):
        default = vdef.get("default", None)
        desc = str(vdef.get("description", "") or "")
        when = vdef.get("when", None) or pkg_when
        raw_values = vdef.get("values", None)
    else:
        default = getattr(vdef, "default", None)
        desc = str(getattr(vdef, "description", "") or "")
        when = getattr(vdef, "when", None) or pkg_when
        raw_values = getattr(vdef, "values", None)

    when_str = str(when).strip() if when else None
    if when_str in ("", "@:"):
        when_str = None

    if raw_values is None or callable(raw_values):
        values = None
    else:
        values = [str(v) for v in raw_values]
        if set(values) in ({"True", "False"}, {"true", "false"}):
            values = None

    return VariantInfo(default=default, description=desc, when=when_str, values=values)


def extract_variants(pkg_class) -> Dict[str, VariantInfo]:
    variants = {}
    for when_spec, variant_dict in getattr(pkg_class, "variants", {}).items():
        pkg_when = str(when_spec).strip() or None
        if not isinstance(variant_dict, dict):
            continue
        for vname, vdef in variant_dict.items():
            variants[str(vname)] = _parse_variant(vdef, pkg_when)
    return variants
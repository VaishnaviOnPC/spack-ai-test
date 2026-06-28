from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class VariantInfo:
    default: Any
    description: str
    when: Optional[str]
    values: Optional[List[Any]]


@dataclass
class DependencyInfo:
    name: str
    bound: str
    dep_type: List[str]
    when: Optional[str]


@dataclass
class RiskSignals:
    cross_language_bindings: bool
    custom_build_system: bool
    compiler_conflict_count: int
    virtual_provider_count: int


@dataclass
class PackageSchema:
    name: str
    versions: List[str]
    variants: Dict[str, VariantInfo]
    dependencies: List[DependencyInfo]
    declared_conflicts: List[Dict[str, str]]
    virtual_deps: List[str]
    risk_signals: RiskSignals
    sha256: str = ""

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "versions": self.versions,
            "variants": {
                k: {
                    "default": v.default,
                    "description": v.description,
                    "when": v.when,
                    "values": v.values,
                }
                for k, v in self.variants.items()
            },
            "dependencies": [
                {"name": d.name, "bound": d.bound, "type": d.dep_type, "when": d.when}
                for d in self.dependencies
            ],
            "declared_conflicts": self.declared_conflicts,
            "virtual_deps": self.virtual_deps,
            "risk_signals": {
                "cross_language_bindings": self.risk_signals.cross_language_bindings,
                "custom_build_system": self.risk_signals.custom_build_system,
                "compiler_conflict_count": self.risk_signals.compiler_conflict_count,
                "virtual_provider_count": self.risk_signals.virtual_provider_count,
            },
            "sha256": self.sha256,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "PackageSchema":
        rs = d.get("risk_signals", {})
        return cls(
            name=d["name"],
            versions=d.get("versions", []),
            variants={
                k: VariantInfo(
                    default=v.get("default"),
                    description=v.get("description", ""),
                    when=v.get("when"),
                    values=v.get("values"),
                )
                for k, v in d.get("variants", {}).items()
            },
            dependencies=[
                DependencyInfo(
                    name=dep["name"],
                    bound=dep.get("bound", ":"),
                    dep_type=dep.get("type", []),
                    when=dep.get("when"),
                )
                for dep in d.get("dependencies", [])
            ],
            declared_conflicts=d.get("declared_conflicts", []),
            virtual_deps=d.get("virtual_deps", []),
            risk_signals=RiskSignals(
                cross_language_bindings=rs.get("cross_language_bindings", False),
                custom_build_system=rs.get("custom_build_system", False),
                compiler_conflict_count=rs.get("compiler_conflict_count", 0),
                virtual_provider_count=rs.get("virtual_provider_count", 0),
            ),
            sha256=d.get("sha256", ""),
        )
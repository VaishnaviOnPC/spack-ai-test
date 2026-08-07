from dataclasses import dataclass, field
from typing import List, Optional

from ai_test.extract.schema import PackageSchema
from ai_test.kb.schema import KBEntry


@dataclass
class MapeContext:
    package_schema: PackageSchema
    kb_entries: List[KBEntry]


@dataclass
class RiskDep:
    name: str
    score: float
    when: Optional[str]
    notes: List[str] = field(default_factory=list)


@dataclass
class CandidateSpec:
    spec_str: str
    concretized: bool
    failure_reason: Optional[str] = None
    installed: bool = False
    install_error: Optional[str] = None
    test_passed: Optional[bool] = None
    test_error: Optional[str] = None

from dataclasses import dataclass
from typing import List, Optional

from ai_test.extract.schema import PackageSchema
from ai_test.kb.schema import KBEntry


@dataclass
class MapeContext:
    package_schema: PackageSchema
    version_failures: List[str]
    kb_entries: List[KBEntry]


@dataclass
class RiskDep:
    name: str
    score: float
    when: Optional[str]


@dataclass
class CandidateSpec:
    spec_str: str
    concretized: bool
    failure_reason: Optional[str] = None

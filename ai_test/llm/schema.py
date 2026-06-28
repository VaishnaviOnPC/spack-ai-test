from dataclasses import dataclass
from typing import List


@dataclass
class LLMResponse:
    package: str
    risk_level: str
    concerns: List[str]
    suggested_specs: List[str]
    raw: str
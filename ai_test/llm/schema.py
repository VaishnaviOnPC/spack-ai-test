from dataclasses import dataclass
from typing import List


@dataclass
class LLMResponse:
    package: str
    suggested_specs: List[str]
    raw: str
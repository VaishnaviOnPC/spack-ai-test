from dataclasses import dataclass
from typing import Optional


@dataclass
class KBEntry:
    pkg_name: str
    spec: str
    concretized: bool
    failure_reason: Optional[str]
    pkg_hash: str
    timestamp: str
    repair_attempts: int = 0
    validation_status: str = "validated"   # "validated" | "ci_queue"
    installed: bool = False
    install_error: Optional[str] = None
    test_passed: Optional[bool] = None
    test_error: Optional[str] = None

import json
import os
from typing import List

from ai_test.kb.schema import KBEntry


def load(path: str) -> List[KBEntry]:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [KBEntry(**e) for e in json.load(f)]


def save(path: str, entries: List[KBEntry]):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        json.dump([e.__dict__ for e in entries], f, indent=2)


def append_entry(path: str, entry: KBEntry):
    entries = load(path)
    entries.append(entry)
    save(path, entries)


def is_known(entries: List[KBEntry], pkg_name: str, spec: str, pkg_hash: str) -> bool:
    return any(
        e.pkg_name == pkg_name and e.spec == spec and e.pkg_hash == pkg_hash
        for e in entries
    )

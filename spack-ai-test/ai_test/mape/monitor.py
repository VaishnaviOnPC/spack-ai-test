from typing import List

from ai_test.extract import extract
from ai_test.kb.store import load as load_kb
from ai_test.mape.schema import MapeContext


def load_context(pkg_name: str, kb_path: str) -> MapeContext:
    schema = extract(pkg_name)
    all_entries = load_kb(kb_path)
    pkg_entries = [e for e in all_entries if e.pkg_name == pkg_name and e.pkg_hash == schema.sha256]
    return MapeContext(package_schema=schema, version_failures=[], kb_entries=pkg_entries)

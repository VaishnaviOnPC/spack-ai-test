import hashlib
import json
import os
from ai_test.extract.schema import PackageSchema


def write_canonical(schema: PackageSchema, output_path: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    d = schema.to_dict()
    raw = json.dumps(d, indent=2, sort_keys=True)
    sha = hashlib.sha256(raw.encode()).hexdigest()
    schema.sha256 = sha
    d["sha256"] = sha
    with open(output_path, "w") as f:
        json.dump(d, f, indent=2, sort_keys=True)
    return sha


def read_canonical(path: str) -> PackageSchema:
    with open(path) as f:
        return PackageSchema.from_dict(json.load(f))
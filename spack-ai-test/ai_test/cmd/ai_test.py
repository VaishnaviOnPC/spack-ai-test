import os
import sys
import traceback
from spack.llnl.util import tty

_ext_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ext_root not in sys.path:
    sys.path.insert(0, _ext_root)


description = "extract and display the package metadata schema for AI-assisted auditing"
section = "analysis"
level = "short"


def setup_parser(subparser):
    subparser.add_argument(
        "package",
        help="name of the Spack package to inspect (e.g. zlib, hdf5, openmpi)",
    )
    subparser.add_argument(
        "--output-dir",
        default=None,
        metavar="DIR",
        help="write canonical.json to this directory",
    )
    subparser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="print raw JSON to stdout instead of the formatted report",
    )


def ai_test(parser, args):
    from ai_test.extract import extract
    from ai_test.printer import print_schema

    pkg_name = args.package
    output_path = None
    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)
        output_path = os.path.join(args.output_dir, "canonical.json")

    tty.msg(f"spack ai-test: extracting metadata for '{pkg_name}'...")

    schema = extract(pkg_name, output_path=output_path)

    if args.json:
        import json
        print(json.dumps(schema.to_dict(), indent=2))
    else:
        print_schema(schema, output_path=output_path)
import os
import sys
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
    subparser.add_argument(
        "--generate",
        action="store_true",
        default=False,
        help="use LLM to generate off-leading-edge test scenarios for this package",
    )
    subparser.add_argument(
        "--model",
        default="claude-haiku-4-5",
        metavar="MODEL",
        help=(
            "model to use for test generation. Provider is detected from the model name. "
            "Anthropic (ANTHROPIC_API_KEY): claude-sonnet-4-6, claude-haiku-4-5. "
            "OpenAI (OPENAI_API_KEY): gpt-4o, gpt-4-turbo. "
            "Gemini (GEMINI_API_KEY): gemini-2.5-pro, gemini-2.5-flash."
        ),
    )


def _print_test_scenarios(result):
    print()
    print(f"Generated Test Scenarios: {result.package}")

    if not result.suggested_specs:
        print()
        print("Could not parse response. Raw output:")
        print(result.raw)
        return

    print()
    for spec in result.suggested_specs:
        print(f"  {spec}")

    print()
    print(f"To validate: spack spec \"{result.suggested_specs[0]}\"")


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

    if args.generate:
        from ai_test.llm import analyze
        tty.msg(f"Generating test scenarios (model: {args.model})")
        result = analyze(schema, model=args.model)
        _print_test_scenarios(result)
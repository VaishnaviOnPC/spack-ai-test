# spack-ai-test

A Spack extension that helps find undeclared compiler and variant compatibility issues. It uses a mix of deterministic checks and an LLM to generate test specs for edge cases that CI usually misses.

## Installation

Clone the repo wherever you keep your Spack extensions:

```bash
git clone https://github.com/VaishnaviOnPC/spack-ai-test /path/to/spack-ai-test
```

Then register it in your `~/.spack/config.yaml`:

```yaml
config:
  extensions:
  - /path/to/spack-ai-test
```

Verify it works:
```bash
spack ai-test --help
```

## Usage

```bash
# Print package info to terminal
spack ai-test zlib

# Dump raw JSON instead
spack ai-test zlib --json

# Save canonical.json report to a directory
spack ai-test hdf5 --output-dir ./reports

# Use an LLM to generate test scenarios for a package
spack ai-test openmpi --generate

# Run the full MAPE-K loop (analyze, generate, test, and save to knowledge base)
spack ai-test openmpi --mape

# Specify a custom model and knowledge base path
spack ai-test openmpi --mape --model gpt-4o --kb ./my_kb.json
```

## Structure
- `ai_test/cmd/ai_test.py`: The main `spack ai-test` CLI command.
- `ai_test/extract/`: Extracts metadata from Spack package classes.
- `ai_test/mape/`: The MAPE-K loop logic (Monitor, Analyze, Plan, Execute).
- `ai_test/llm/`: Prompts and API clients for generating specs.
- `ai_test/kb/`: Local JSON knowledge base for caching test results.

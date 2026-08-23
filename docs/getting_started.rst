.. _getting_started:

===============
Getting Started
===============

This guide walks you through setting up and running your first test with ``spack ai-test``.

A note on terminology: a **leading-edge** configuration is what most CI pipelines test —
the newest package version, the latest compiler, and all default variants. This tool targets
**off-leading-edge** configurations: older version pins, non-default variants, and dependency
combinations that are rarely (if ever) tested but frequently encountered by real users.

Prerequisites
=============

Before installing ``spack-ai-test``, ensure you have:

* **Spack** (v0.21 or later) installed and available in your ``PATH``.
* **Python** 3.9 or higher.
* An API key for at least one supported LLM provider:

  * **Google Gemini** (``GEMINI_API_KEY``)
  * **Anthropic Claude** (``ANTHROPIC_API_KEY``)
  * **OpenAI** (``OPENAI_API_KEY``)

Installation
============

``spack-ai-test`` is packaged as a standard Spack command extension.

1. Clone the Extension Repository
---------------------------------

Clone the repository to a convenient location on your system — for example, alongside other
Spack extensions or in your home directory:

.. code-block:: console

   $ git clone https://github.com/VaishnaviOnPC/spack-ai-test.git /path/to/spack-ai-test

2. Register the Extension in Spack
-----------------------------------

Add the cloned directory to the ``extensions`` list in your Spack configuration
(e.g., ``~/.spack/config.yaml``):

.. code-block:: yaml

   config:
     extensions:
       - /path/to/spack-ai-test

Alternatively, register it directly from the command line:

.. code-block:: console

   $ spack config add "config:extensions:[/path/to/spack-ai-test]"

3. Verify Installation
----------------------

Check that Spack recognizes the extension:

.. code-block:: console

   $ spack ai-test --help

You should see the command description and the full list of available flags.

Configuring API Keys
====================

Export your preferred provider's API key in your shell environment before running any
generation commands:

.. code-block:: console

   # Google Gemini (default)
   $ export GEMINI_API_KEY="your-gemini-api-key"

   # Anthropic Claude
   $ export ANTHROPIC_API_KEY="your-anthropic-api-key"

   # OpenAI
   $ export OPENAI_API_KEY="your-openai-api-key"

.. note::
   Default models and settings can also be configured in ``~/.spack/ai_test.yaml``.
   See :ref:`configuration` for details.

.. warning::
   If no API key is set for the selected model, the tool raises an error at the Plan stage
   before any concretization is attempted. Inspection commands (``spack ai-test <package>``
   without ``--mape`` or ``--generate``) do not require an API key.

Running Your First Test
=======================

To inspect a package's metadata and computed risk signals without invoking the LLM:

.. code-block:: console

   $ spack ai-test zlib

The output lists the extracted versions, variants, declared dependency constraints, and a
set of computed risk signals — for example, unbounded version ranges or virtual provider
dependencies. No API key is required for this step.

To run the full self-adaptive testing loop against locally installed compilers:

.. code-block:: console

   $ spack ai-test zlib --mape --local --model gemini-2.5-flash

The tool prints one result line per generated spec (``[PASS]``, ``[FAIL]``, or
``[BUILD_FAIL]``) followed by a totals summary showing how many specs were tested,
concretized, and failed.

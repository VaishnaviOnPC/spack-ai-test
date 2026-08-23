.. _configuration:

=============
Configuration
=============

``spack-ai-test`` provides a layered configuration system that follows standard Spack conventions.

Configuration Precedence
========================

Settings are resolved in the following order of precedence (highest to lowest):

1. **Command-line flags** (e.g., ``--model``, ``--kb``)
2. **Environment variables** (e.g., ``SPACK_AI_TEST_MODEL``, ``SPACK_AI_TEST_KB``)
3. **Configuration file** (``~/.spack/ai_test.yaml``)
4. **Built-in defaults**

Configuration File: ``ai_test.yaml``
====================================

You can customize default behavior by creating or editing ``~/.spack/ai_test.yaml``:

.. code-block:: yaml

   ai_test:
     # Default LLM model identifier
     model: gemini-2.5-flash

     # Default path for the persistent Knowledge Base
     kb: ~/.spack/cache/ai_test/kb.json

     # Compiler matrix used when queuing specs for external CI
     ci_compilers:
       - gcc@11.4.0
       - gcc@12.3.0
       - gcc@13.3.0
       - clang@14.0.0
       - clang@16.0.0

Configuration Options
---------------------

.. list-table::
   :widths: 20 20 60
   :header-rows: 1

   * - Option
     - Default Value
     - Description
   * - ``model``
     - ``gemini-2.5-flash``
     - Default LLM model string for spec generation.
   * - ``kb``
     - ``~/.spack/cache/ai_test/kb.json``
     - Path to the local JSON Knowledge Base. The file and any parent directories are created
       automatically on the first run if they do not exist.
   * - ``ci_compilers``
     - *(List of GCC & Clang versions)*
     - The compiler matrix used when running without ``--local``. Specs targeting compilers
       not installed on the current machine are saved to the KB as ``ci_queue`` entries rather
       than tested immediately. If this list is left unconfigured, it defaults to a broad matrix
       defined in ``config.py``. Reduce it to only the compilers present on your cluster to
       avoid accumulating untested queue entries.

Environment Variables
=====================

The following environment variables are recognized:

API Keys
--------

* ``GEMINI_API_KEY``: API authentication key for Google Gemini models.
* ``ANTHROPIC_API_KEY``: API authentication key for Anthropic Claude models.
* ``OPENAI_API_KEY``: API authentication key for OpenAI GPT models.

Extension Overrides
-------------------

* ``SPACK_AI_TEST_MODEL``: Overrides the default model specified in ``ai_test.yaml``.
* ``SPACK_AI_TEST_KB``: Overrides the Knowledge Base path specified in ``ai_test.yaml``.

Supported LLM Models
====================

``spack-ai-test`` includes built-in client support for leading model families:

.. list-table::
   :widths: 25 35 40
   :header-rows: 1

   * - Provider
     - Model String (``--model``)
     - Required Environment Variable
   * - **Google Gemini**
     - ``gemini-2.5-flash``, ``gemini-2.5-pro``
     - ``GEMINI_API_KEY``
   * - **Anthropic Claude**
     - ``claude-sonnet-4-6``, ``claude-haiku-4-5``
     - ``ANTHROPIC_API_KEY``
   * - **OpenAI**
     - ``gpt-4o``, ``gpt-4-turbo``
     - ``OPENAI_API_KEY``

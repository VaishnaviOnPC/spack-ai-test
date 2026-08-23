.. _command_reference:

=================
Command Reference
=================

This page documents the full command-line interface for the ``spack ai-test`` command.

-----------------
``spack ai-test``
-----------------

Synopsis
========

.. code-block:: console

   $ spack ai-test [-h] [--output-dir DIR] [--json] [--generate] [--mape]
                   [--plan-only] [--execute-queued] [--kb PATH] [--build]
                   [--test] [--local] [--model MODEL] [--no-retrieval]
                   [--score SPEC] [--bisect]
                   package

Description
===========

Extract package metadata, compute structural dependency risk metrics, and run
LLM-assisted combinatorial testing to discover compatibility and build failures across
the Spack configuration space.

Arguments
=========

.. option:: package

   Name of the Spack package to inspect or test (e.g., ``zlib``, ``hdf5``, ``openmpi``).
   A compiler constraint may be appended directly using standard Spack spec syntax
   (e.g., ``openmpi%gcc@13.3.0``).

Options
=======

Information & Diagnostics
--------------------------

.. option:: --json

   Print the raw canonical JSON package schema to stdout instead of the default
   formatted terminal output.

.. option:: --output-dir DIR

   Write the canonical schema (``canonical.json``) into the specified directory.

.. option:: --score SPEC

   Compute and display the structural and empirical risk score for a user-provided
   spec string. Skips LLM generation and concretization entirely.

Execution Modes
---------------

.. option:: --generate

   Prompt the LLM to generate candidate off-leading-edge test specifications based on the
   extracted package schema and risk analysis. Does not execute concretization or write
   to the Knowledge Base.

.. option:: --mape

   Execute the complete self-adaptive loop: analyze risk, generate candidate specs,
   statically validate them, test concretization via Spack's ASP solver, and record
   results in the Knowledge Base.

.. option:: --plan-only

   **Login-node mode.** Generate candidate test specs via the LLM and queue them in the
   Knowledge Base with status ``pending``. Does not attempt concretization or compilation.
   Intended for use on internet-connected login nodes before submitting a batch job.

.. option:: --execute-queued

   **Compute-node mode.** Process all ``pending`` specs stored in the Knowledge Base.
   Requires no internet access or LLM connectivity. Intended for use inside a Slurm or
   PBS batch script on a compute node.

Execution Depth
---------------

.. option:: --build

   When used with ``--mape`` or ``--execute-queued``, attempt to build each successfully
   concretized spec via ``spack install`` to detect compilation failures.

.. option:: --test

   When used with ``--mape`` or ``--execute-queued``, install the package and run its
   test suite (``spack install --test=root``) to detect regression failures.
   Implies ``--build``.

.. option:: --bisect

   On a deterministic build or test failure, automatically bisect the package's version
   history to identify the regression. Uses exponential galloping to establish bounds,
   then binary search to isolate the exact version. Transient failures — such as network
   timeouts or parallel-make race conditions — are filtered out by a confirmatory second
   build attempt before bisection begins.

Context & Environment
---------------------

.. option:: --local

   Restrict spec generation to compilers that are locally installed and visible to Spack.
   Avoids queuing specs that target unavailable toolchains.

.. option:: --no-retrieval

   Disable Version Gap Analysis and historical KB Pattern Mining during prompt construction.
   The LLM still receives the package schema, risk scores, and KB history, but not the
   live registry and pattern-mining context. Useful for comparing generation quality with
   and without retrieval augmentation.

.. option:: --model MODEL

   LLM model identifier to use for spec generation. Overrides the value in ``ai_test.yaml``.

.. option:: --kb PATH

   Path to an alternative JSON Knowledge Base file. Overrides the value in ``ai_test.yaml``.

Examples
========

Display metadata and risk analysis for a package:

.. code-block:: console

   $ spack ai-test openmpi

Generate candidate specs pinned to a specific compiler:

.. code-block:: console

   $ spack ai-test openmpi%gcc@13.3.0 --generate

Run the full automated testing loop against locally installed compilers:

.. code-block:: console

   $ spack ai-test zlib --mape --local --test

Decoupled cluster workflow — generate on the login node, execute in a batch job:

.. code-block:: console

   # Step 1: Login node (internet required)
   $ spack ai-test hdf5 --plan-only --model gemini-2.5-flash

   # Step 2: Compute node batch script (no internet required)
   $ spack ai-test hdf5 --execute-queued --test --bisect

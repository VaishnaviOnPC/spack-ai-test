.. _workflows:

==================
Advanced Workflows
==================

This section covers advanced automated testing workflows, including closed-loop
execution, cluster-based offline testing, and automated failure bisection.

The MAPE-K Self-Adaptive Loop
=============================

The ``--mape`` flag runs the full self-adaptive testing cycle:

.. code-block:: console

   $ spack ai-test openmpi --mape --local

The pipeline executes through four coordinated stages:

1. **Monitor**: Retrieves accumulated test history from the Knowledge Base (``kb.json``) matching the package schema hash.
2. **Analyze**: Calculates empirical failure rates and prioritizes high-risk dependency branches.
3. **Plan**: Prompts the LLM with multi-source RAG context (live registry version gaps, historical failure patterns, and active GitHub issue signals).
4. **Execute**:
   * Pre-validates generated specs statically against the package schema.
   * Concretizes valid specs with Spack's internal ASP solver.
   * Persists test outcomes (pass, concretize failure, build failure) back to the Knowledge Base.

The terminal prints a single header line summarising the package state (KB entry count,
failure rate, active compiler), followed by one result line per spec, then a totals
line at the end. For example::

   openmpi | KB: 12 entries | failure rate: 0.42 (5/12) | compiler: gcc@13.3.0
   [PASS]  openmpi@4.1.5 +pmi %gcc@13.3.0
   [FAIL]  openmpi@4.0.7 +cuda %gcc@13.3.0
   [PASS]  openmpi@4.1.6 ~shared %gcc@13.3.0
   3 tested | 2 concretized | 1 failed -> ~/.spack/cache/ai_test/kb.json

Testing Depth: Build and Regression Testing
===========================================

By default, ``--mape`` validates that specs concretize. To extend testing to compilation and test suites:

Building Concretized Specs
--------------------------

To compile concretized specs via ``spack install``:

.. code-block:: console

   $ spack ai-test zlib --mape --local --build

Running Package Test Suites
---------------------------

To compile and execute the package test suite (``spack install --test=root``):

.. code-block:: console

   $ spack ai-test zlib --mape --local --test

.. note::
   Passing ``--test`` automatically implies ``--build``.

HPC Cluster Workflows (Offline / Compute Nodes)
===============================================

In High Performance Computing (HPC) clusters, compute nodes frequently lack external
internet access required to reach LLM APIs. ``spack ai-test`` provides a decoupled workflow
to handle this environment:

Phase 1: Login Node (Online Generation)
---------------------------------------

On a login or edge node with internet connectivity, generate candidate specs and queue them in the Knowledge Base:

.. code-block:: console

   $ spack ai-test openmpi --plan-only --model gemini-2.5-flash

This saves generated specs to ``kb.json`` with a status of ``pending`` without running concretization or builds.

Phase 2: Compute Node (Offline Execution)
-----------------------------------------

In a compute node batch script (e.g., Slurm job) without internet connectivity:

.. code-block:: console

   $ spack ai-test openmpi --execute-queued --test

This reads all ``pending`` specs from the Knowledge Base, concretizes them, builds the packages, and records the test outcomes.

Automated Failure Bisection
===========================

When a package build or test fails, determining the exact version where the regression occurred
can be tedious. Adding ``--bisect`` enables automated failure localization:

.. code-block:: console

   $ spack ai-test openmpi --mape --test --bisect

When a deterministic failure occurs on package version :math:`v_{\text{fail}}`:

1. **Exponential Galloping**: The system tests predecessor versions in powers of two (:math:`1, 2, 4, 8, \dots`) to establish a bounding range between a passing version and a failing version.
2. **Binary Search**: Once bounded, it performs a binary search to identify the exact commit or release version where the regression was introduced.

Knowledge Base
==============

The Knowledge Base (``kb.json``) stores historical test outcomes keyed by package schema hash.

* **Deduplication**: Previously tested configurations are never re-tested, so repeated runs
  of ``--mape`` progressively explore new parts of the configuration space.
* **Schema Versioning**: When a ``package.py`` changes (e.g., a new version is added), the
  schema hash changes and the package's KB history resets automatically. Prior data for that
  package is preserved but becomes inactive.
* **Pattern Mining**: Features with high failure rates across accumulated tests (e.g., a
  specific variant flag or compiler) are automatically surfaced as risk context in future
  LLM prompts, improving generation quality over time.

Inspecting the Knowledge Base
------------------------------

The KB is a plain JSON file located by default at ``~/.spack/cache/ai_test/kb.json``.
It is human-readable and can be inspected directly:

.. code-block:: console

   $ cat ~/.spack/cache/ai_test/kb.json | python -m json.tool | head -60

Resetting the Knowledge Base
-----------------------------

To clear the history for a specific package, delete entries with its ``pkg_name`` field
from the JSON file. To reset the entire KB:

.. code-block:: console

   $ rm ~/.spack/cache/ai_test/kb.json

The file is re-created automatically on the next run.

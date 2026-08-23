.. _basic_usage:

===========
Basic Usage
===========

This section covers the core command-line workflows for inspecting package metadata,
computing risk scores, and generating candidate test configurations.

Inspecting Package Metadata
===========================

Running ``spack ai-test <package>`` extracts and displays structured metadata directly
from the package recipe (``package.py``):

.. code-block:: console

   $ spack ai-test hdf5

This output provides:

* **Declared Versions & Preferred Version**: Lists available releases and identifies
  the leading-edge version.
* **Variants**: Groups boolean and multi-valued variants along with their default values.
* **Dependencies & Version Constraints**: Summarizes direct dependencies, version bounds,
  and activation conditions (``when=``).
* **Risk Signals**: Highlights structural risk factors such as unbounded dependency ranges
  (``:``), multi-major version spans, virtual providers (e.g., ``mpi``), and C++ ABI linkage.

Raw JSON Schema Export
======================

To emit the canonical JSON representation of a package's schema for automated processing
or CI auditing:

.. code-block:: console

   $ spack ai-test hdf5 --json

To write the schema directly to a file (``canonical.json``) inside a target directory:

.. code-block:: console

   $ spack ai-test hdf5 --output-dir ./schema_reports

Evaluating Spec Risk Scores
===========================

You can compute the risk score of a specific, user-provided spec without invoking the LLM:

.. code-block:: console

   $ spack ai-test hdf5 --score "hdf5@1.14.0 +cxx +fortran %gcc@13.3.0"

The scoring engine evaluates the spec against the package dependency graph and historical
Knowledge Base data, displaying:

* **Structural Score**: A multiplicative score combining unbounded version ranges, version
  spans across major releases, C++ ABI exposure, and virtual dependency depth.
* **Amplification Factor**: A dynamic weight based on historical failure rates in the
  Knowledge Base. On a fresh installation with no KB history, this factor is ``1.0``.
* **Final Risk Score**: The combined metric used by the planning engine to steer LLM
  generation toward high-risk configuration regions.

Generating Test Scenarios
=========================

To invoke the LLM and generate off-leading-edge test specifications without running
concretization:

.. code-block:: console

   $ spack ai-test openmpi --generate

The language model receives the extracted schema and risk context, and outputs 3–5
candidate spec strings. Each spec is printed on its own line and can be passed directly
to ``spack spec`` for manual verification.

.. note::
   ``--generate`` does not write anything to the Knowledge Base. To run the full loop
   including concretization and KB persistence, use ``--mape``. See :ref:`workflows`
   for details.

Targeting Specific Compilers
============================

A compiler constraint can be appended directly to the package argument using standard
Spack spec syntax:

.. code-block:: console

   $ spack ai-test openmpi%gcc@13.3.0 --generate

This pins the compiler for both schema analysis and LLM prompt construction. On cluster
environments where only specific compilers are installed, add ``--local`` to restrict
generation to locally available compilers only:

.. code-block:: console

   $ spack ai-test openmpi%gcc@13.3.0 --mape --local

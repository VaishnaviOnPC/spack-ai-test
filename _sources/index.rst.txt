.. _spack_ai_test:

=============================================
spack-ai-test: AI-Assisted Package Testing
=============================================

``spack ai-test`` is a Spack extension for AI-assisted configuration testing of HPC
packages. It uses Large Language Models (LLMs) to generate candidate build configurations
that are deliberately targeted at high-risk, underexplored corners of a package's
configuration space — version ranges, compiler variants, and dependency combinations that
standard CI pipelines never reach.

The extension integrates directly with your existing Spack installation. You can use it
interactively on a workstation, or as part of a batch testing workflow on an HPC cluster.

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   getting_started
   basic_usage
   workflows
   configuration

.. toctree::
   :maxdepth: 2
   :caption: Reference

   command_reference

Indices and tables
==================

* :ref:`genindex`
* :ref:`search`



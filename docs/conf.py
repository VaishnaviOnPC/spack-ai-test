import os
import sys


project = "spack-ai-test"
copyright = "2025, Vaishnavi Mishra, CERN-HSF GSoC"
author = "Vaishnavi Mishra"
release = "0.1.0"


extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.mathjax",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
source_suffix = ".rst"
master_doc = "index"


html_theme = "sphinx_rtd_theme"
html_theme_options = {
    "navigation_depth": 3,
    "collapse_navigation": False,
    "sticky_navigation": True,
    "titles_only": False,
}
html_static_path = ["_static"]
html_title = "spack-ai-test Documentation"



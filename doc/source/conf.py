import os
import sys

sys.path.insert(0, os.path.abspath('../..'))  # Needed for examples.

import defopt

# -- General configuration ------------------------------------------------

needs_sphinx = '1.5.2'
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.intersphinx',
    'sphinx.ext.napoleon',
    'sphinx_autodoc_typehints',
]

source_suffix = '.rst'
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']
master_doc = 'index'

project = 'defopt'
copyright = '2016–present, Evan Andrews, Antony Lee'
author = 'Evan Andrews, Antony Lee'

version = release = defopt.__version__

language = 'en'

default_role = 'py:obj'

pygments_style = 'sphinx'

todo_include_todos = False

# -- Options for HTML output ----------------------------------------------

html_theme = 'alabaster'
html_sidebars = {'**': ['about.html', 'navigation.html', 'localtoc.html']}
html_theme_options = {
    'description': 'A lightweight, no-effort argument parser.',
    'github_user': 'anntzer',
    'github_repo': 'defopt',
    'github_banner': True,
    'github_button': False,
    'code_font_size': '80%',
}
# html_last_updated_fmt = ''  # bitprophet/alabaster#93

htmlhelp_basename = 'defopt_doc'

# -- Options for LaTeX output ---------------------------------------------

latex_elements = {}
latex_documents = [(
    master_doc,
    'defopt.tex',
    'defopt Documentation',
    author,
    'manual',
)]

# -- Options for manual page output ---------------------------------------

man_pages = [(
    master_doc,
    'defopt',
    'defopt Documentation',
    [author],
    1,
)]

# -- Options for Texinfo output -------------------------------------------

texinfo_documents = [(
    master_doc,
    'defopt',
    'defopt Documentation',
    author,
    'defopt',
    'A lightweight, no-effort argument parser.',
    'Miscellaneous',
)]

# -- Misc. configuration --------------------------------------------------

autodoc_member_order = 'bysource'

intersphinx_mapping = {
    'python': ('https://docs.python.org/3.8', None),
    'sphinx': ('http://www.sphinx-doc.org/en/latest/', None),
}

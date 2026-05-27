# Configuration file for the Sphinx documentation builder.
# https://www.sphinx-doc.org/en/master/usage/configuration.html

from __future__ import annotations

# -- Project information ------------------------------------------------------

project = "AgentSUMO"
author = "Minwoo Jeong, Jeeyun Chang, Yoonjin Yoon"
copyright = (
    "2026, KAIST Graduate School of Data Science · "
    "AgentSUMO Documentation"
)
release = "0.1.0"
version = "0.1"

# -- General configuration ----------------------------------------------------

extensions = [
    "myst_parser",
    "sphinx_copybutton",
    "sphinxcontrib.mermaid",
    "sphinx_design",
    "sphinx_togglebutton",
    "sphinx.ext.intersphinx",
    "sphinx.ext.autosectionlabel",
    "notfound.extension",
]

source_suffix = {
    ".md": "markdown",
    ".rst": "restructuredtext",
}

master_doc = "index"
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
templates_path = ["_templates"]

# Avoid duplicate-label warnings when autosectionlabel sees common headings.
autosectionlabel_prefix_document = True
autosectionlabel_maxdepth = 2

# -- MyST Markdown ------------------------------------------------------------

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "tasklist",
    "attrs_inline",
    "linkify",
    "substitution",
    "fieldlist",
]
myst_heading_anchors = 3

# -- HTML output (PyData Sphinx Theme) ----------------------------------------

html_theme = "pydata_sphinx_theme"
html_title = "AgentSUMO"
html_static_path = ["_static"]
html_css_files = ["custom.css"]
# Logo is configured via html_theme_options below (light/dark variants).
# html_favicon left unset until a favicon is added; PyData falls back gracefully.

html_theme_options = {
    "logo": {
        "image_light": "_static/logo_light.png",
        "image_dark": "_static/logo_dark.png",
        "alt_text": "AgentSUMO",
    },
    "github_url": "https://github.com/mw-jeong/AgentSUMO",
    "icon_links": [
        {
            "name": "arXiv",
            "url": "https://arxiv.org/abs/2511.06804",
            "icon": "fa-solid fa-newspaper",
            "type": "fontawesome",
        },
    ],
    "use_edit_page_button": False,
    "show_toc_level": 2,
    "show_nav_level": 1,
    "navigation_depth": 4,
    "collapse_navigation": False,
    "navbar_align": "left",
    "navbar_center": ["navbar-nav"],
    "navbar_end": ["theme-switcher", "navbar-icon-links"],
    "secondary_sidebar_items": ["page-toc"],
    "footer_start": ["copyright"],
    "footer_end": ["sphinx-version", "theme-version"],
    "pygments_light_style": "tango",
    "pygments_dark_style": "github-dark",
    "search_bar_text": "Search the docs…",
    "search_as_you_type": True,
    "back_to_top_button": True,
}

html_context = {
    "github_user": "mw-jeong",
    "github_repo": "AgentSUMO",
    "github_version": "main",
    "doc_path": "docs",
    "default_mode": "dark",  # PyData Sphinx Theme template var: force dark by default
}

# -- Extension options --------------------------------------------------------

mermaid_version = "10.9.0"
mermaid_init_js = """
mermaid.initialize({
  startOnLoad: true,
  theme: 'base',
  themeVariables: {
    primaryColor: '#5b8c00',
    primaryTextColor: '#dce8e3',
    primaryBorderColor: '#7ab800',
    lineColor: '#7ab800',
    secondaryColor: '#111518',
    tertiaryColor: '#0c0f12',
    background: '#080a0c',
    mainBkg: '#111518',
    nodeTextColor: '#dce8e3',
    edgeLabelBackground: '#0c0f12'
  }
});
"""

copybutton_prompt_text = r">>> |\$ |# "
copybutton_prompt_is_regexp = True

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

notfound_context = {
    "title": "Page not found",
    "body": "<h1>Page not found</h1><p>Sorry, we couldn't find that page. Try the sidebar or the search bar.</p>",
}

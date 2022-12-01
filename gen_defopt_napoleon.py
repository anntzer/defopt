"""
Autogenerate standalone _defopt_napoleon module from sphinx.ext.napoleon.

Run ``python gen_defopt_napoleon.py .../napoleon.py > lib/_defopt_napoleon.py``
and manually update the version number in LICENSE and the configuration in
_parse_docstring.
"""


from argparse import ArgumentParser
import ast
import tokenize


parser = ArgumentParser()
parser.add_argument("napoleon_docstring_path")
args = parser.parse_args()
with tokenize.open(args.napoleon_docstring_path) as file:
    src = file.read()
tree = ast.parse(src)


class AnnotationRemover(ast.NodeTransformer):
    def visit_FunctionDef(self, node):
        self.generic_visit(node)
        if hasattr(node, "returns"):
            del node.returns
        for arg in node.args.args:
            if hasattr(arg, "annotation"):
                del arg.annotation
        return node

    def visit_AnnAssign(self, node):
        self.generic_visit(node)
        if not hasattr(node, "value"):
            return
        assign = ast.Assign([node.target], node.value)
        assign.lineno = node.lineno
        assign.end_lineno = node.end_lineno
        assign.col_offset = node.col_offset
        assign.end_col_offset = node.end_col_offset
        return assign


AnnotationRemover().visit(tree)
src = ast.unparse(tree)


replacements = [
    ("from sphinx.application import Sphinx\n", ""),
    ("from sphinx.config import Config as SphinxConfig\n", ""),
    ("from sphinx.locale import _, __\n",
     "_ = __ = lambda s: s\n"),
    ("from sphinx.util import logging\n",
     "import logging\n"),
    ("from sphinx.util.inspect import stringify_annotation\n",
     "def stringify_annotation(_): pass\n"),
    ("from sphinx.util.typing import get_type_hints\n",
     "from typing import get_type_hints\n"),
]
for a, b in replacements:
    assert src.count(a) == 1
    src = src.replace(a, b)


print(src)

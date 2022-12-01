"""Classes for docstring parsing and formatting."""
import collections
import inspect
import re
from functools import partial
from typing import Any, Callable, Dict, List, Tuple, Union
_ = __ = lambda s: s
import logging
def stringify_annotation(_): pass
from typing import get_type_hints
logger = logging.getLogger(__name__)
_directive_regex = re.compile('\\.\\. \\S+::')
_google_section_regex = re.compile('^(\\s|\\w)+:\\s*$')
_google_typed_arg_regex = re.compile('(.+?)\\(\\s*(.*[^\\s]+)\\s*\\)')
_numpy_section_regex = re.compile('^[=\\-`:\\\'"~^_*+#<>]{2,}\\s*$')
_single_colon_regex = re.compile('(?<!:):(?!:)')
_xref_or_code_regex = re.compile('((?::(?:[a-zA-Z0-9]+[\\-_+:.])*[a-zA-Z0-9]+:`.+?`)|(?:``.+?``))')
_xref_regex = re.compile('(?:(?::(?:[a-zA-Z0-9]+[\\-_+:.])*[a-zA-Z0-9]+:)?`.+?`)')
_bullet_list_regex = re.compile('^(\\*|\\+|\\-)(\\s+\\S|\\s*$)')
_enumerated_list_regex = re.compile('^(?P<paren>\\()?(\\d+|#|[ivxlcdm]+|[IVXLCDM]+|[a-zA-Z])(?(paren)\\)|\\.)(\\s+\\S|\\s*$)')
_token_regex = re.compile('(,\\sor\\s|\\sor\\s|\\sof\\s|:\\s|\\sto\\s|,\\sand\\s|\\sand\\s|,\\s|[{]|[}]|"(?:\\\\"|[^"])*"|\'(?:\\\\\'|[^\'])*\')')
_default_regex = re.compile('^default[^_0-9A-Za-z].*$')
_SINGLETONS = ('None', 'True', 'False', 'Ellipsis')

class Deque(collections.deque):
    """
    A subclass of deque that mimics ``pockets.iterators.modify_iter``.

    The `.Deque.get` and `.Deque.next` methods are added.
    """
    sentinel = object()

    def get(self, n):
        """
        Return the nth element of the stack, or ``self.sentinel`` if n is
        greater than the stack size.
        """
        return self[n] if n < len(self) else self.sentinel

    def next(self):
        if self:
            return super().popleft()
        else:
            raise StopIteration

def _convert_type_spec(_type, translations={}):
    """Convert type specification to reference in reST."""
    if _type in translations:
        return translations[_type]
    elif _type == 'None':
        return ':obj:`None`'
    else:
        return ':class:`%s`' % _type
    return _type

class GoogleDocstring:
    """Convert Google style docstrings to reStructuredText.

    Parameters
    ----------
    docstring : :obj:`str` or :obj:`list` of :obj:`str`
        The docstring to parse, given either as a string or split into
        individual lines.
    config: :obj:`sphinx.ext.napoleon.Config` or :obj:`sphinx.config.Config`
        The configuration settings to use. If not given, defaults to the
        config object on `app`; or if `app` is not given defaults to the
        a new :class:`sphinx.ext.napoleon.Config` object.


    Other Parameters
    ----------------
    app : :class:`sphinx.application.Sphinx`, optional
        Application object representing the Sphinx process.
    what : :obj:`str`, optional
        A string specifying the type of the object to which the docstring
        belongs. Valid values: "module", "class", "exception", "function",
        "method", "attribute".
    name : :obj:`str`, optional
        The fully qualified name of the object.
    obj : module, class, exception, function, method, or attribute
        The object to which the docstring belongs.
    options : :class:`sphinx.ext.autodoc.Options`, optional
        The options given to the directive: an object with attributes
        inherited_members, undoc_members, show_inheritance and noindex that
        are True if the flag option of same name was given to the auto
        directive.


    Example
    -------
    >>> from sphinx.ext.napoleon import Config
    >>> config = Config(napoleon_use_param=True, napoleon_use_rtype=True)
    >>> docstring = '''One line summary.
    ...
    ... Extended description.
    ...
    ... Args:
    ...   arg1(int): Description of `arg1`
    ...   arg2(str): Description of `arg2`
    ... Returns:
    ...   str: Description of return value.
    ... '''
    >>> print(GoogleDocstring(docstring, config))
    One line summary.
    <BLANKLINE>
    Extended description.
    <BLANKLINE>
    :param arg1: Description of `arg1`
    :type arg1: int
    :param arg2: Description of `arg2`
    :type arg2: str
    <BLANKLINE>
    :returns: Description of return value.
    :rtype: str
    <BLANKLINE>

    """
    _name_rgx = re.compile('^\\s*((?::(?P<role>\\S+):)?`(?P<name>~?[a-zA-Z0-9_.-]+)`| (?P<name2>~?[a-zA-Z0-9_.-]+))\\s*', re.X)

    def __init__(self, docstring, config=None, app=None, what='', name='', obj=None, options=None):
        self._config = config
        self._app = app
        if not self._config:
            from sphinx.ext.napoleon import Config
            self._config = self._app.config if self._app else Config()
        if not what:
            if inspect.isclass(obj):
                what = 'class'
            elif inspect.ismodule(obj):
                what = 'module'
            elif callable(obj):
                what = 'function'
            else:
                what = 'object'
        self._what = what
        self._name = name
        self._obj = obj
        self._opt = options
        if isinstance(docstring, str):
            lines = docstring.splitlines()
        else:
            lines = docstring
        self._lines = Deque(map(str.rstrip, lines))
        self._parsed_lines = []
        self._is_in_section = False
        self._section_indent = 0
        if not hasattr(self, '_directive_sections'):
            self._directive_sections = []
        if not hasattr(self, '_sections'):
            self._sections = {'args': self._parse_parameters_section, 'arguments': self._parse_parameters_section, 'attention': partial(self._parse_admonition, 'attention'), 'attributes': self._parse_attributes_section, 'caution': partial(self._parse_admonition, 'caution'), 'danger': partial(self._parse_admonition, 'danger'), 'error': partial(self._parse_admonition, 'error'), 'example': self._parse_examples_section, 'examples': self._parse_examples_section, 'hint': partial(self._parse_admonition, 'hint'), 'important': partial(self._parse_admonition, 'important'), 'keyword args': self._parse_keyword_arguments_section, 'keyword arguments': self._parse_keyword_arguments_section, 'methods': self._parse_methods_section, 'note': partial(self._parse_admonition, 'note'), 'notes': self._parse_notes_section, 'other parameters': self._parse_other_parameters_section, 'parameters': self._parse_parameters_section, 'receive': self._parse_receives_section, 'receives': self._parse_receives_section, 'return': self._parse_returns_section, 'returns': self._parse_returns_section, 'raise': self._parse_raises_section, 'raises': self._parse_raises_section, 'references': self._parse_references_section, 'see also': self._parse_see_also_section, 'tip': partial(self._parse_admonition, 'tip'), 'todo': partial(self._parse_admonition, 'todo'), 'warning': partial(self._parse_admonition, 'warning'), 'warnings': partial(self._parse_admonition, 'warning'), 'warn': self._parse_warns_section, 'warns': self._parse_warns_section, 'yield': self._parse_yields_section, 'yields': self._parse_yields_section}
        self._load_custom_sections()
        self._parse()

    def __str__(self):
        """Return the parsed docstring in reStructuredText format.

        Returns
        -------
        unicode
            Unicode version of the docstring.

        """
        return '\n'.join(self.lines())

    def lines(self):
        """Return the parsed lines of the docstring in reStructuredText format.

        Returns
        -------
        list(str)
            The lines of the docstring in a list.

        """
        return self._parsed_lines

    def _consume_indented_block(self, indent=1):
        lines = []
        line = self._lines.get(0)
        while not self._is_section_break() and (not line or self._is_indented(line, indent)):
            lines.append(self._lines.next())
            line = self._lines.get(0)
        return lines

    def _consume_contiguous(self):
        lines = []
        while self._lines and self._lines.get(0) and (not self._is_section_header()):
            lines.append(self._lines.next())
        return lines

    def _consume_empty(self):
        lines = []
        line = self._lines.get(0)
        while self._lines and (not line):
            lines.append(self._lines.next())
            line = self._lines.get(0)
        return lines

    def _consume_field(self, parse_type=True, prefer_type=False):
        line = self._lines.next()
        (before, colon, after) = self._partition_field_on_colon(line)
        (_name, _type, _desc) = (before, '', after)
        if parse_type:
            match = _google_typed_arg_regex.match(before)
            if match:
                _name = match.group(1).strip()
                _type = match.group(2)
        _name = self._escape_args_and_kwargs(_name)
        if prefer_type and (not _type):
            (_type, _name) = (_name, _type)
        if _type and self._config.napoleon_preprocess_types:
            _type = _convert_type_spec(_type, self._config.napoleon_type_aliases or {})
        indent = self._get_indent(line) + 1
        _descs = [_desc] + self._dedent(self._consume_indented_block(indent))
        _descs = self.__class__(_descs, self._config).lines()
        return (_name, _type, _descs)

    def _consume_fields(self, parse_type=True, prefer_type=False, multiple=False):
        self._consume_empty()
        fields = []
        while not self._is_section_break():
            (_name, _type, _desc) = self._consume_field(parse_type, prefer_type)
            if multiple and _name:
                for name in _name.split(','):
                    fields.append((name.strip(), _type, _desc))
            elif _name or _type or _desc:
                fields.append((_name, _type, _desc))
        return fields

    def _consume_inline_attribute(self):
        line = self._lines.next()
        (_type, colon, _desc) = self._partition_field_on_colon(line)
        if not colon or not _desc:
            (_type, _desc) = (_desc, _type)
            _desc += colon
        _descs = [_desc] + self._dedent(self._consume_to_end())
        _descs = self.__class__(_descs, self._config).lines()
        return (_type, _descs)

    def _consume_returns_section(self, preprocess_types=False):
        lines = self._dedent(self._consume_to_next_section())
        if lines:
            (before, colon, after) = self._partition_field_on_colon(lines[0])
            (_name, _type, _desc) = ('', '', lines)
            if colon:
                if after:
                    _desc = [after] + lines[1:]
                else:
                    _desc = lines[1:]
                _type = before
            if _type and preprocess_types and self._config.napoleon_preprocess_types:
                _type = _convert_type_spec(_type, self._config.napoleon_type_aliases or {})
            _desc = self.__class__(_desc, self._config).lines()
            return [(_name, _type, _desc)]
        else:
            return []

    def _consume_usage_section(self):
        lines = self._dedent(self._consume_to_next_section())
        return lines

    def _consume_section_header(self):
        section = self._lines.next()
        stripped_section = section.strip(':')
        if stripped_section.lower() in self._sections:
            section = stripped_section
        return section

    def _consume_to_end(self):
        lines = []
        while self._lines:
            lines.append(self._lines.next())
        return lines

    def _consume_to_next_section(self):
        self._consume_empty()
        lines = []
        while not self._is_section_break():
            lines.append(self._lines.next())
        return lines + self._consume_empty()

    def _dedent(self, lines, full=False):
        if full:
            return [line.lstrip() for line in lines]
        else:
            min_indent = self._get_min_indent(lines)
            return [line[min_indent:] for line in lines]

    def _escape_args_and_kwargs(self, name):
        if name.endswith('_') and getattr(self._config, 'strip_signature_backslash', False):
            name = name[:-1] + '\\_'
        if name[:2] == '**':
            return '\\*\\*' + name[2:]
        elif name[:1] == '*':
            return '\\*' + name[1:]
        else:
            return name

    def _fix_field_desc(self, desc):
        if self._is_list(desc):
            desc = [''] + desc
        elif desc[0].endswith('::'):
            desc_block = desc[1:]
            indent = self._get_indent(desc[0])
            block_indent = self._get_initial_indent(desc_block)
            if block_indent > indent:
                desc = [''] + desc
            else:
                desc = ['', desc[0]] + self._indent(desc_block, 4)
        return desc

    def _format_admonition(self, admonition, lines):
        lines = self._strip_empty(lines)
        if len(lines) == 1:
            return ['.. %s:: %s' % (admonition, lines[0].strip()), '']
        elif lines:
            lines = self._indent(self._dedent(lines), 3)
            return ['.. %s::' % admonition, ''] + lines + ['']
        else:
            return ['.. %s::' % admonition, '']

    def _format_block(self, prefix, lines, padding=None):
        if lines:
            if padding is None:
                padding = ' ' * len(prefix)
            result_lines = []
            for (i, line) in enumerate(lines):
                if i == 0:
                    result_lines.append((prefix + line).rstrip())
                elif line:
                    result_lines.append(padding + line)
                else:
                    result_lines.append('')
            return result_lines
        else:
            return [prefix]

    def _format_docutils_params(self, fields, field_role='param', type_role='type'):
        lines = []
        for (_name, _type, _desc) in fields:
            _desc = self._strip_empty(_desc)
            if any(_desc):
                _desc = self._fix_field_desc(_desc)
                field = ':%s %s: ' % (field_role, _name)
                lines.extend(self._format_block(field, _desc))
            else:
                lines.append(':%s %s:' % (field_role, _name))
            if _type:
                lines.append(':%s %s: %s' % (type_role, _name, _type))
        return lines + ['']

    def _format_field(self, _name, _type, _desc):
        _desc = self._strip_empty(_desc)
        has_desc = any(_desc)
        separator = ' -- ' if has_desc else ''
        if _name:
            if _type:
                if '`' in _type:
                    field = '**%s** (%s)%s' % (_name, _type, separator)
                else:
                    field = '**%s** (*%s*)%s' % (_name, _type, separator)
            else:
                field = '**%s**%s' % (_name, separator)
        elif _type:
            if '`' in _type:
                field = '%s%s' % (_type, separator)
            else:
                field = '*%s*%s' % (_type, separator)
        else:
            field = ''
        if has_desc:
            _desc = self._fix_field_desc(_desc)
            if _desc[0]:
                return [field + _desc[0]] + _desc[1:]
            else:
                return [field] + _desc
        else:
            return [field]

    def _format_fields(self, field_type, fields):
        field_type = ':%s:' % field_type.strip()
        padding = ' ' * len(field_type)
        multi = len(fields) > 1
        lines = []
        for (_name, _type, _desc) in fields:
            field = self._format_field(_name, _type, _desc)
            if multi:
                if lines:
                    lines.extend(self._format_block(padding + ' * ', field))
                else:
                    lines.extend(self._format_block(field_type + ' * ', field))
            else:
                lines.extend(self._format_block(field_type + ' ', field))
        if lines and lines[-1]:
            lines.append('')
        return lines

    def _get_current_indent(self, peek_ahead=0):
        line = self._lines.get(peek_ahead)
        while line is not self._lines.sentinel:
            if line:
                return self._get_indent(line)
            peek_ahead += 1
            line = self._lines.get(peek_ahead)
        return 0

    def _get_indent(self, line):
        for (i, s) in enumerate(line):
            if not s.isspace():
                return i
        return len(line)

    def _get_initial_indent(self, lines):
        for line in lines:
            if line:
                return self._get_indent(line)
        return 0

    def _get_min_indent(self, lines):
        min_indent = None
        for line in lines:
            if line:
                indent = self._get_indent(line)
                if min_indent is None:
                    min_indent = indent
                elif indent < min_indent:
                    min_indent = indent
        return min_indent or 0

    def _indent(self, lines, n=4):
        return [' ' * n + line for line in lines]

    def _is_indented(self, line, indent=1):
        for (i, s) in enumerate(line):
            if i >= indent:
                return True
            elif not s.isspace():
                return False
        return False

    def _is_list(self, lines):
        if not lines:
            return False
        if _bullet_list_regex.match(lines[0]):
            return True
        if _enumerated_list_regex.match(lines[0]):
            return True
        if len(lines) < 2 or lines[0].endswith('::'):
            return False
        indent = self._get_indent(lines[0])
        next_indent = indent
        for line in lines[1:]:
            if line:
                next_indent = self._get_indent(line)
                break
        return next_indent > indent

    def _is_section_header(self):
        section = self._lines.get(0).lower()
        match = _google_section_regex.match(section)
        if match and section.strip(':') in self._sections:
            header_indent = self._get_indent(section)
            section_indent = self._get_current_indent(peek_ahead=1)
            return section_indent > header_indent
        elif self._directive_sections:
            if _directive_regex.match(section):
                for directive_section in self._directive_sections:
                    if section.startswith(directive_section):
                        return True
        return False

    def _is_section_break(self):
        line = self._lines.get(0)
        return not self._lines or self._is_section_header() or (self._is_in_section and line and (not self._is_indented(line, self._section_indent)))

    def _load_custom_sections(self):
        if self._config.napoleon_custom_sections is not None:
            for entry in self._config.napoleon_custom_sections:
                if isinstance(entry, str):
                    self._sections[entry.lower()] = self._parse_custom_generic_section
                elif entry[1] == 'params_style':
                    self._sections[entry[0].lower()] = self._parse_custom_params_style_section
                elif entry[1] == 'returns_style':
                    self._sections[entry[0].lower()] = self._parse_custom_returns_style_section
                else:
                    self._sections[entry[0].lower()] = self._sections.get(entry[1].lower(), self._parse_custom_generic_section)

    def _parse(self):
        self._parsed_lines = self._consume_empty()
        if self._name and self._what in ('attribute', 'data', 'property'):
            res = []
            try:
                res = self._parse_attribute_docstring()
            except StopIteration:
                pass
            self._parsed_lines.extend(res)
            return
        while self._lines:
            if self._is_section_header():
                try:
                    section = self._consume_section_header()
                    self._is_in_section = True
                    self._section_indent = self._get_current_indent()
                    if _directive_regex.match(section):
                        lines = [section] + self._consume_to_next_section()
                    else:
                        lines = self._sections[section.lower()](section)
                finally:
                    self._is_in_section = False
                    self._section_indent = 0
            elif not self._parsed_lines:
                lines = self._consume_contiguous() + self._consume_empty()
            else:
                lines = self._consume_to_next_section()
            self._parsed_lines.extend(lines)

    def _parse_admonition(self, admonition, section):
        lines = self._consume_to_next_section()
        return self._format_admonition(admonition, lines)

    def _parse_attribute_docstring(self):
        (_type, _desc) = self._consume_inline_attribute()
        lines = self._format_field('', '', _desc)
        if _type:
            lines.extend(['', ':type: %s' % _type])
        return lines

    def _parse_attributes_section(self, section):
        lines = []
        for (_name, _type, _desc) in self._consume_fields():
            if not _type:
                _type = self._lookup_annotation(_name)
            if self._config.napoleon_use_ivar:
                field = ':ivar %s: ' % _name
                lines.extend(self._format_block(field, _desc))
                if _type:
                    lines.append(':vartype %s: %s' % (_name, _type))
            else:
                lines.append('.. attribute:: ' + _name)
                if self._opt and 'noindex' in self._opt:
                    lines.append('   :noindex:')
                lines.append('')
                fields = self._format_field('', '', _desc)
                lines.extend(self._indent(fields, 3))
                if _type:
                    lines.append('')
                    lines.extend(self._indent([':type: %s' % _type], 3))
                lines.append('')
        if self._config.napoleon_use_ivar:
            lines.append('')
        return lines

    def _parse_examples_section(self, section):
        labels = {'example': _('Example'), 'examples': _('Examples')}
        use_admonition = self._config.napoleon_use_admonition_for_examples
        label = labels.get(section.lower(), section)
        return self._parse_generic_section(label, use_admonition)

    def _parse_custom_generic_section(self, section):
        return self._parse_generic_section(section, False)

    def _parse_custom_params_style_section(self, section):
        return self._format_fields(section, self._consume_fields())

    def _parse_custom_returns_style_section(self, section):
        fields = self._consume_returns_section(preprocess_types=True)
        return self._format_fields(section, fields)

    def _parse_usage_section(self, section):
        header = ['.. rubric:: Usage:', '']
        block = ['.. code-block:: python', '']
        lines = self._consume_usage_section()
        lines = self._indent(lines, 3)
        return header + block + lines + ['']

    def _parse_generic_section(self, section, use_admonition):
        lines = self._strip_empty(self._consume_to_next_section())
        lines = self._dedent(lines)
        if use_admonition:
            header = '.. admonition:: %s' % section
            lines = self._indent(lines, 3)
        else:
            header = '.. rubric:: %s' % section
        if lines:
            return [header, ''] + lines + ['']
        else:
            return [header, '']

    def _parse_keyword_arguments_section(self, section):
        fields = self._consume_fields()
        if self._config.napoleon_use_keyword:
            return self._format_docutils_params(fields, field_role='keyword', type_role='kwtype')
        else:
            return self._format_fields(_('Keyword Arguments'), fields)

    def _parse_methods_section(self, section):
        lines = []
        for (_name, _type, _desc) in self._consume_fields(parse_type=False):
            lines.append('.. method:: %s' % _name)
            if self._opt and 'noindex' in self._opt:
                lines.append('   :noindex:')
            if _desc:
                lines.extend([''] + self._indent(_desc, 3))
            lines.append('')
        return lines

    def _parse_notes_section(self, section):
        use_admonition = self._config.napoleon_use_admonition_for_notes
        return self._parse_generic_section(_('Notes'), use_admonition)

    def _parse_other_parameters_section(self, section):
        if self._config.napoleon_use_param:
            fields = self._consume_fields(multiple=True)
            return self._format_docutils_params(fields)
        else:
            fields = self._consume_fields()
            return self._format_fields(_('Other Parameters'), fields)

    def _parse_parameters_section(self, section):
        if self._config.napoleon_use_param:
            fields = self._consume_fields(multiple=True)
            return self._format_docutils_params(fields)
        else:
            fields = self._consume_fields()
            return self._format_fields(_('Parameters'), fields)

    def _parse_raises_section(self, section):
        fields = self._consume_fields(parse_type=False, prefer_type=True)
        lines = []
        for (_name, _type, _desc) in fields:
            m = self._name_rgx.match(_type)
            if m and m.group('name'):
                _type = m.group('name')
            elif _xref_regex.match(_type):
                pos = _type.find('`')
                _type = _type[pos + 1:-1]
            _type = ' ' + _type if _type else ''
            _desc = self._strip_empty(_desc)
            _descs = ' ' + '\n    '.join(_desc) if any(_desc) else ''
            lines.append(':raises%s:%s' % (_type, _descs))
        if lines:
            lines.append('')
        return lines

    def _parse_receives_section(self, section):
        if self._config.napoleon_use_param:
            fields = self._consume_fields(multiple=True)
            return self._format_docutils_params(fields)
        else:
            fields = self._consume_fields()
            return self._format_fields(_('Receives'), fields)

    def _parse_references_section(self, section):
        use_admonition = self._config.napoleon_use_admonition_for_references
        return self._parse_generic_section(_('References'), use_admonition)

    def _parse_returns_section(self, section):
        fields = self._consume_returns_section()
        multi = len(fields) > 1
        use_rtype = False if multi else self._config.napoleon_use_rtype
        lines = []
        for (_name, _type, _desc) in fields:
            if use_rtype:
                field = self._format_field(_name, '', _desc)
            else:
                field = self._format_field(_name, _type, _desc)
            if multi:
                if lines:
                    lines.extend(self._format_block('          * ', field))
                else:
                    lines.extend(self._format_block(':returns: * ', field))
            else:
                if any(field):
                    lines.extend(self._format_block(':returns: ', field))
                if _type and use_rtype:
                    lines.extend([':rtype: %s' % _type, ''])
        if lines and lines[-1]:
            lines.append('')
        return lines

    def _parse_see_also_section(self, section):
        return self._parse_admonition('seealso', section)

    def _parse_warns_section(self, section):
        return self._format_fields(_('Warns'), self._consume_fields())

    def _parse_yields_section(self, section):
        fields = self._consume_returns_section(preprocess_types=True)
        return self._format_fields(_('Yields'), fields)

    def _partition_field_on_colon(self, line):
        before_colon = []
        after_colon = []
        colon = ''
        found_colon = False
        for (i, source) in enumerate(_xref_or_code_regex.split(line)):
            if found_colon:
                after_colon.append(source)
            else:
                m = _single_colon_regex.search(source)
                if i % 2 == 0 and m:
                    found_colon = True
                    colon = source[m.start():m.end()]
                    before_colon.append(source[:m.start()])
                    after_colon.append(source[m.end():])
                else:
                    before_colon.append(source)
        return (''.join(before_colon).strip(), colon, ''.join(after_colon).strip())

    def _strip_empty(self, lines):
        if lines:
            start = -1
            for (i, line) in enumerate(lines):
                if line:
                    start = i
                    break
            if start == -1:
                lines = []
            end = -1
            for i in reversed(range(len(lines))):
                line = lines[i]
                if line:
                    end = i
                    break
            if start > 0 or end + 1 < len(lines):
                lines = lines[start:end + 1]
        return lines

    def _lookup_annotation(self, _name):
        if self._config.napoleon_attr_annotations:
            if self._what in ('module', 'class', 'exception') and self._obj:
                if not hasattr(self, '_annotations'):
                    localns = getattr(self._config, 'autodoc_type_aliases', {})
                    localns.update(getattr(self._config, 'napoleon_type_aliases', {}) or {})
                    self._annotations = get_type_hints(self._obj, None, localns)
                if _name in self._annotations:
                    return stringify_annotation(self._annotations[_name])
        return ''

def _recombine_set_tokens(tokens):
    token_queue = collections.deque(tokens)
    keywords = ('optional', 'default')

    def takewhile_set(tokens):
        open_braces = 0
        previous_token = None
        while True:
            try:
                token = tokens.popleft()
            except IndexError:
                break
            if token == ', ':
                previous_token = token
                continue
            if not token.strip():
                continue
            if token in keywords:
                tokens.appendleft(token)
                if previous_token is not None:
                    tokens.appendleft(previous_token)
                break
            if previous_token is not None:
                yield previous_token
                previous_token = None
            if token == '{':
                open_braces += 1
            elif token == '}':
                open_braces -= 1
            yield token
            if open_braces == 0:
                break

    def combine_set(tokens):
        while True:
            try:
                token = tokens.popleft()
            except IndexError:
                break
            if token == '{':
                tokens.appendleft('{')
                yield ''.join(takewhile_set(tokens))
            else:
                yield token
    return list(combine_set(token_queue))

def _tokenize_type_spec(spec):

    def postprocess(item):
        if _default_regex.match(item):
            default = item[:7]
            other = item[8:]
            return [default, ' ', other]
        else:
            return [item]
    tokens = [item for raw_token in _token_regex.split(spec) for item in postprocess(raw_token) if item]
    return tokens

def _token_type(token, location=None):

    def is_numeric(token):
        try:
            complex(token)
        except ValueError:
            return False
        else:
            return True
    if token.startswith(' ') or token.endswith(' '):
        type_ = 'delimiter'
    elif is_numeric(token) or (token.startswith('{') and token.endswith('}')) or (token.startswith('"') and token.endswith('"')) or (token.startswith("'") and token.endswith("'")):
        type_ = 'literal'
    elif token.startswith('{'):
        logger.warning(__('invalid value set (missing closing brace): %s'), token, location=location)
        type_ = 'literal'
    elif token.endswith('}'):
        logger.warning(__('invalid value set (missing opening brace): %s'), token, location=location)
        type_ = 'literal'
    elif token.startswith("'") or token.startswith('"'):
        logger.warning(__('malformed string literal (missing closing quote): %s'), token, location=location)
        type_ = 'literal'
    elif token.endswith("'") or token.endswith('"'):
        logger.warning(__('malformed string literal (missing opening quote): %s'), token, location=location)
        type_ = 'literal'
    elif token in ('optional', 'default'):
        type_ = 'control'
    elif _xref_regex.match(token):
        type_ = 'reference'
    else:
        type_ = 'obj'
    return type_

def _convert_numpy_type_spec(_type, location=None, translations={}):

    def convert_obj(obj, translations, default_translation):
        translation = translations.get(obj, obj)
        if translation in _SINGLETONS and default_translation == ':class:`%s`':
            default_translation = ':obj:`%s`'
        elif translation == '...' and default_translation == ':class:`%s`':
            default_translation = ':obj:`%s <Ellipsis>`'
        if _xref_regex.match(translation) is None:
            translation = default_translation % translation
        return translation
    tokens = _tokenize_type_spec(_type)
    combined_tokens = _recombine_set_tokens(tokens)
    types = [(token, _token_type(token, location)) for token in combined_tokens]
    converters = {'literal': lambda x: '``%s``' % x, 'obj': lambda x: convert_obj(x, translations, ':class:`%s`'), 'control': lambda x: '*%s*' % x, 'delimiter': lambda x: x, 'reference': lambda x: x}
    converted = ''.join((converters.get(type_)(token) for (token, type_) in types))
    return converted

class NumpyDocstring(GoogleDocstring):
    """Convert NumPy style docstrings to reStructuredText.

    Parameters
    ----------
    docstring : :obj:`str` or :obj:`list` of :obj:`str`
        The docstring to parse, given either as a string or split into
        individual lines.
    config: :obj:`sphinx.ext.napoleon.Config` or :obj:`sphinx.config.Config`
        The configuration settings to use. If not given, defaults to the
        config object on `app`; or if `app` is not given defaults to the
        a new :class:`sphinx.ext.napoleon.Config` object.


    Other Parameters
    ----------------
    app : :class:`sphinx.application.Sphinx`, optional
        Application object representing the Sphinx process.
    what : :obj:`str`, optional
        A string specifying the type of the object to which the docstring
        belongs. Valid values: "module", "class", "exception", "function",
        "method", "attribute".
    name : :obj:`str`, optional
        The fully qualified name of the object.
    obj : module, class, exception, function, method, or attribute
        The object to which the docstring belongs.
    options : :class:`sphinx.ext.autodoc.Options`, optional
        The options given to the directive: an object with attributes
        inherited_members, undoc_members, show_inheritance and noindex that
        are True if the flag option of same name was given to the auto
        directive.


    Example
    -------
    >>> from sphinx.ext.napoleon import Config
    >>> config = Config(napoleon_use_param=True, napoleon_use_rtype=True)
    >>> docstring = '''One line summary.
    ...
    ... Extended description.
    ...
    ... Parameters
    ... ----------
    ... arg1 : int
    ...     Description of `arg1`
    ... arg2 : str
    ...     Description of `arg2`
    ... Returns
    ... -------
    ... str
    ...     Description of return value.
    ... '''
    >>> print(NumpyDocstring(docstring, config))
    One line summary.
    <BLANKLINE>
    Extended description.
    <BLANKLINE>
    :param arg1: Description of `arg1`
    :type arg1: int
    :param arg2: Description of `arg2`
    :type arg2: str
    <BLANKLINE>
    :returns: Description of return value.
    :rtype: str
    <BLANKLINE>

    Methods
    -------
    __str__()
        Return the parsed docstring in reStructuredText format.

        Returns
        -------
        str
            UTF-8 encoded version of the docstring.

    __unicode__()
        Return the parsed docstring in reStructuredText format.

        Returns
        -------
        unicode
            Unicode version of the docstring.

    lines()
        Return the parsed lines of the docstring in reStructuredText format.

        Returns
        -------
        list(str)
            The lines of the docstring in a list.

    """

    def __init__(self, docstring, config=None, app=None, what='', name='', obj=None, options=None):
        self._directive_sections = ['.. index::']
        super().__init__(docstring, config, app, what, name, obj, options)

    def _get_location(self):
        try:
            filepath = inspect.getfile(self._obj) if self._obj is not None else None
        except TypeError:
            filepath = None
        name = self._name
        if filepath is None and name is None:
            return None
        elif filepath is None:
            filepath = ''
        return ':'.join([filepath, 'docstring of %s' % name])

    def _escape_args_and_kwargs(self, name):
        func = super()._escape_args_and_kwargs
        if ', ' in name:
            return ', '.join((func(param) for param in name.split(', ')))
        else:
            return func(name)

    def _consume_field(self, parse_type=True, prefer_type=False):
        line = self._lines.next()
        if parse_type:
            (_name, _, _type) = self._partition_field_on_colon(line)
        else:
            (_name, _type) = (line, '')
        (_name, _type) = (_name.strip(), _type.strip())
        _name = self._escape_args_and_kwargs(_name)
        if parse_type and (not _type):
            _type = self._lookup_annotation(_name)
        if prefer_type and (not _type):
            (_type, _name) = (_name, _type)
        if self._config.napoleon_preprocess_types:
            _type = _convert_numpy_type_spec(_type, location=self._get_location(), translations=self._config.napoleon_type_aliases or {})
        indent = self._get_indent(line) + 1
        _desc = self._dedent(self._consume_indented_block(indent))
        _desc = self.__class__(_desc, self._config).lines()
        return (_name, _type, _desc)

    def _consume_returns_section(self, preprocess_types=False):
        return self._consume_fields(prefer_type=True)

    def _consume_section_header(self):
        section = self._lines.next()
        if not _directive_regex.match(section):
            self._lines.next()
        return section

    def _is_section_break(self):
        (line1, line2) = (self._lines.get(0), self._lines.get(1))
        return not self._lines or self._is_section_header() or ['', ''] == [line1, line2] or (self._is_in_section and line1 and (not self._is_indented(line1, self._section_indent)))

    def _is_section_header(self):
        (section, underline) = (self._lines.get(0), self._lines.get(1))
        section = section.lower()
        if section in self._sections and isinstance(underline, str):
            return bool(_numpy_section_regex.match(underline))
        elif self._directive_sections:
            if _directive_regex.match(section):
                for directive_section in self._directive_sections:
                    if section.startswith(directive_section):
                        return True
        return False

    def _parse_see_also_section(self, section):
        lines = self._consume_to_next_section()
        try:
            return self._parse_numpydoc_see_also_section(lines)
        except ValueError:
            return self._format_admonition('seealso', lines)

    def _parse_numpydoc_see_also_section(self, content):
        """
        Derived from the NumpyDoc implementation of _parse_see_also.

        See Also
        --------
        func_name : Descriptive text
            continued text
        another_func_name : Descriptive text
        func_name1, func_name2, :meth:`func_name`, func_name3

        """
        items = []

        def parse_item_name(text):
            """Match ':role:`name`' or 'name'"""
            m = self._name_rgx.match(text)
            if m:
                g = m.groups()
                if g[1] is None:
                    return (g[3], None)
                else:
                    return (g[2], g[1])
            raise ValueError('%s is not a item name' % text)

        def push_item(name, rest):
            if not name:
                return
            (name, role) = parse_item_name(name)
            items.append((name, list(rest), role))
            del rest[:]

        def translate(func, description, role):
            translations = self._config.napoleon_type_aliases
            if role is not None or not translations:
                return (func, description, role)
            translated = translations.get(func, func)
            match = self._name_rgx.match(translated)
            if not match:
                return (translated, description, role)
            groups = match.groupdict()
            role = groups['role']
            new_func = groups['name'] or groups['name2']
            return (new_func, description, role)
        current_func = None
        rest = []
        for line in content:
            if not line.strip():
                continue
            m = self._name_rgx.match(line)
            if m and line[m.end():].strip().startswith(':'):
                push_item(current_func, rest)
                (current_func, line) = (line[:m.end()], line[m.end():])
                rest = [line.split(':', 1)[1].strip()]
                if not rest[0]:
                    rest = []
            elif not line.startswith(' '):
                push_item(current_func, rest)
                current_func = None
                if ',' in line:
                    for func in line.split(','):
                        if func.strip():
                            push_item(func, [])
                elif line.strip():
                    current_func = line
            elif current_func is not None:
                rest.append(line.strip())
        push_item(current_func, rest)
        if not items:
            return []
        items = [translate(func, description, role) for (func, description, role) in items]
        lines = []
        last_had_desc = True
        for (name, desc, role) in items:
            if role:
                link = ':%s:`%s`' % (role, name)
            else:
                link = ':obj:`%s`' % name
            if desc or last_had_desc:
                lines += ['']
                lines += [link]
            else:
                lines[-1] += ', %s' % link
            if desc:
                lines += self._indent([' '.join(desc)])
                last_had_desc = True
            else:
                last_had_desc = False
        lines += ['']
        return self._format_admonition('seealso', lines)

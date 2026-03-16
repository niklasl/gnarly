import re
from typing import Iterator, NamedTuple, TextIO

from pyoxigraph import (BlankNode, DefaultGraph, Literal, NamedNode, Quad,
                        RdfFormat, Store, Triple, parse)

from . import (RDF_NIL_NODE, RDF_TYPE_NODE, RDFNS, Description, Frame, List,
               Node, Statement, Term)

RDF_DIRLANGSTRING_NODE = NamedNode(f"{RDFNS}dirLangString")
RDF_LANGSTRING_NODE = NamedNode(f"{RDFNS}langString")
XSDNS = "http://www.w3.org/2001/XMLSchema#"
XSD_STRING_NODE = NamedNode(f"{XSDNS}string")
XSD_INTEGER_NODE = NamedNode(f"{XSDNS}integer")
XSD_DECIMAL_NODE = NamedNode(f"{XSDNS}decimal")
XSD_DOUBLE_NODE = NamedNode(f"{XSDNS}double")
XSD_BOOLEAN_NODE = NamedNode(f"{XSDNS}boolean")

LEAF_RE = re.compile(r'(.*?)([^#/:]+)$')

PNAME_LOCAL_ESC = re.compile(r"([~!$&'()*+,;=/?#@]|^[.-]|[.-]$|%(?![0-9A-Fa-f]{2}))")

LINEBREAK = re.compile('[\n\r]')


class TrigFormatOptions(NamedTuple):
    indent: str = '  '
    max_width: int = 88
    sparql_keywords: bool = True
    long_annotation_newline: bool = False
    end_annotation_newline: bool = True
    end_bnode_newline: bool = True
    force_type_oneline: bool = False
    long: bool = False


class TurtleFormatter:
    prefixes: dict[str, str]
    ns_to_prefix: dict[str, str]
    base_iri: str | None

    def __init__(self, prefixes, base_iri):
        self.prefixes = prefixes
        self.ns_to_prefix = {ns: pfx for pfx, ns in prefixes.items()}
        self.base_iri = base_iri

    def shorten(self, iri: str):
        if iri in self.ns_to_prefix:
            return f"{self.ns_to_prefix[iri]}:"

        parts = LEAF_RE.split(iri)
        if len(parts) == 4 and parts[1] != '' and parts[1] in self.ns_to_prefix:
            lname = self.lname(parts[2])
            return f"{self.ns_to_prefix[parts[1]]}:{lname}"

        if self.base_iri and iri.startswith(self.base_iri):
            iri = iri[len(self.base_iri) :]

        return f'<{iri}>'

    def lname(self, v: str) -> str:
        return PNAME_LOCAL_ESC.sub(r'\\\1', v)

    def stringrepr(self, v: str) -> str:
        if LINEBREAK.search(v) is not None:
            return self.to_multiline_str(v)
        else:
            return f'"{self.clean(v)}"'

    def clean(self, v: str) -> str:
        v = v.replace('\\', '\\\\')
        v = v.replace('\r', '\\r')
        v = v.replace('\n', '\\n')
        v = v.replace('"', r'\"')
        return v

    def to_multiline_str(self, v: str) -> str:
        v = v.replace('"""', '\\"\\"\\"')
        if v.endswith('"') and not v.endswith('\\"'):
            v = f'{v[0 : len(v) - 1]}\\"'
        return f'"""{v}"""'

    def to_str(self, n: Description | Term) -> str:
        if n == RDF_NIL_NODE:
            return '()'
        match n:
            case Description():
                return self.to_str(n.subject)
            case Triple(s, p, o):
                pr = "a" if p == RDF_TYPE_NODE else self.to_str(p)
                return f'<<( {self.to_str(s)} {pr} {self.to_str(o)} )>>'
            case Literal(_):
                v = n.value
                if n.datatype == RDF_DIRLANGSTRING_NODE:
                    return f'{self.stringrepr(v)}@{n.language}--{n.direction}'
                elif n.datatype == RDF_LANGSTRING_NODE:
                    return f'{self.stringrepr(v)}@{n.language}'
                elif n.datatype == XSD_STRING_NODE:
                    return f'{self.stringrepr(v)}'
                elif n.datatype == XSD_BOOLEAN_NODE:
                    return v
                elif n.datatype == XSD_INTEGER_NODE:
                    return v
                elif n.datatype == XSD_DECIMAL_NODE:
                    return f"{v}.0" if "." not in v else v
                elif n.datatype == XSD_DOUBLE_NODE:
                    return v + 'e0'
                else:
                    v = v.replace('"', r'\"')
                    return f'{self.stringrepr(v)}^^{self.to_str(n.datatype)}'
            case NamedNode(v):
                return self.shorten(v)
            case BlankNode(v):
                return f'_:{n.value}'


class TrigSerializer:
    out: TextIO
    fmt: TurtleFormatter
    options: TrigFormatOptions
    _pfx_decl: str
    _base_decl: str

    _indent: str
    _level: int
    _pending_separator: str | None
    _pending_predicate: str | None
    _linewidth: int
    _just_indented: bool

    def __init__(
        self,
        out: TextIO,
        prefixes: dict[str, str],
        base_iri: str | None,
        options: TrigFormatOptions | None = None,
    ):
        self.out = out
        self.fmt = TurtleFormatter(prefixes, base_iri)
        self.options = options or TrigFormatOptions()
        self._level = 0
        self._update_indent()
        self._pending_separator = None
        self._pending_predicate = None
        self._linewidth = 0
        self._just_indented = False

        if self.options.sparql_keywords:
            self._pfx_decl = "PREFIX {}: <{}>"
            self._base_decl = "BASE <{}>"
        else:
            self._pfx_decl = "@prefix {}: <{}> ."
            self._base_decl = "@base <{}> ."

    def indent(self):
        self._level += 1
        self._update_indent()

    def dedent(self):
        self._level -= 1
        self._update_indent()

    def _update_indent(self):
        self._indent = self.options.indent * self._level

    def serialize(self, frame: Frame) -> None:
        self.write_prelude()
        self.write_dataset(frame)

    def write_dataset(self, frame: Frame) -> None:
        graphkey = "GRAPH " if self.options.sparql_keywords else ""
        self.serialize_graph(frame)
        for name, frame in frame.get_named_descriptions():
            self.writeln()
            self.write_line(graphkey + self.fmt.to_str(name) + " {")
            self.indent()
            self.serialize_graph(frame)
            self.dedent()
            self.writeln()
            self.write_line("}")

    def serialize_graph(self, frame: Frame) -> None:
        descriptions = frame.get_descriptions()
        for desc in sorted(descriptions):
            self.writeln()
            self.write_description(desc)

    def write_prelude(self) -> None:
        for pfx, ns in self.fmt.prefixes.items():
            self.write_line(self._pfx_decl.format(pfx, ns))

        if self.fmt.base_iri is not None:
            self.write_line(self._base_decl.format(self.fmt.base_iri))

    def write_description(self, desc: Description):
        s_str = "[]" if desc.is_pure_blank() else self.fmt.to_str(desc.subject)

        reifies = list(desc.get_reifies())
        if len(reifies) > 0:
            if desc.is_pure_blank():
                rs = ""
            else:
                rs = f"~ {s_str} "
            if len(reifies) > 1:
                for triple in reifies:
                    ts, tp, to = triple
                    trpl_s = self.fmt.to_str(triple)[3:-3]
                    self.write_indent()
                    self.write_line(f'<<{trpl_s}{rs}>> .')
            else:
                trpl_s = self.fmt.to_str(reifies[0])[3:-3]
                s_str = f'<<{trpl_s}{rs}>>'

        self.write_indent()

        if desc.list_items is not None:
            self.write_list(desc.list_items, keeplevel=True)
            s_str = ""

        self.write_opt_predicate(s_str)
        self.indent()
        multiple = self.write_description_body(desc)

        if multiple and self.options.long:
            self.write_line(" ;")
            self.dedent()
            self.write_indent()
            self.write_line(".")
        else:
            self.write_line(" .")
            self.dedent()

    def write_description_body(self, desc: Description) -> bool:
        c = 1 if self.write_types(desc) else 0
        if c == 0 and desc.has_multiple_statements():
            self._pending_separator = ""
        c += self.write_statements(desc)
        return c > 1

    def write_types(self, desc: Description) -> bool:
        typerepr = self.get_typerepr(desc)
        self.write(typerepr)
        return typerepr != ""

    def get_typerepr(self, desc) -> str:
        typereprs = sorted(self.fmt.to_str(t) for t in desc.get_simple_types())
        overflowed = (
            (self.options.long and desc.has_multiple_statements())
            or not self.options.force_type_oneline
            and (
                self._linewidth + 3 + sum(len(t) + 2 for t in typereprs)
                > self.options.max_width
            )
        )
        joiner = (
            f" ;\n{self.options.indent * self._level}a "
            if self.options.long
            else (
                f" ,\n{self.options.indent * (self._level + 1)}"
                if overflowed
                else " , "
            )
        )
        types = joiner.join(typereprs)
        if types:
            lead = f"\n{self._indent}" if overflowed else " "
            self._pending_separator = " ;"
            return f"{lead}a {types}"
        else:
            return ""

    def write_statements(self, desc: Description) -> int:
        statements = sorted(desc.get_regular_statements())

        prev_p: NamedNode | None = None

        for p, stmt in statements:
            same_p = p == prev_p

            if same_p:
                self._pending_separator = " ," if not self.options.long else " ;"

            if self._pending_separator is not None:
                self.write_line(self._pending_separator)
                self._linewidth = 0
                self._pending_separator = None
                self.write_indent()

            if same_p and not self.options.long:
                self.write(self.options.indent)
            else:
                self._pending_predicate = (
                    "a" if p == RDF_TYPE_NODE else self.fmt.to_str(p)
                )

            prev_p = p

            self.write_object(stmt)

            self._pending_separator = " ;"

        self._pending_separator = None

        return len(statements)

    def write_object(self, stmt: Statement) -> None:
        if isinstance(stmt.o, Description) and stmt.o.list_items is not None:
            self.write_list(stmt.o.list_items)
            return

        o: Description | Term | None
        if isinstance(stmt.o, Description):
            o = stmt.o.subject
            if self.attempt_write_blank(stmt.o):
                o = None
        else:
            o = stmt.o

        if o is not None:
            self.write_opt_predicate(self.fmt.to_str(o))

        self.write_annotations(stmt)

    def write_annotations(self, stmt) -> None:
        annotations = sorted(stmt.get_annotations())
        isnext = (
            len(annotations) > 1
            or self.options.long_annotation_newline
            and any(annot.has_multiple_statements() for annot in annotations)
        )
        prev_named = False
        keep_same_line = (
            all(not annot.is_embeddable_annotation() for annot in annotations)
            and self._linewidth
            + sum(len(self.fmt.to_str(annot.subject)) + 3 for annot in annotations)
            < self.options.max_width
        )

        for annot in annotations:
            if annot.is_embeddable_annotation():
                self.indent()
                self.indent()
                space = " "

                if isnext and not keep_same_line:
                    self.writeln()
                    self.write_indent()
                    space = ""

                self.indent()
                if prev_named:
                    space += "~ "
                self.write_opt_predicate(space + "{|")
                multiple = self.write_description_body(annot)
                self.dedent()

                if multiple and self.options.end_annotation_newline:
                    self.writeln()
                    self.write_indent()
                    self.write("|}")
                else:
                    self.write(" |}")

                self.dedent()
                self.dedent()
            else:
                if isnext and not keep_same_line:
                    self.indent()
                    self.indent()
                    self.writeln()
                    self.write_indent()
                    space = ""
                else:
                    space = " "

                self.write(space + "~ ")
                self.write(self.fmt.to_str(annot.subject))
                prev_named = True

                if isnext and not keep_same_line:
                    self.dedent()
                    self.dedent()

            isnext = True

    def attempt_write_blank(self, desc: object) -> bool:
        if not isinstance(desc, Description):
            return False
        if desc.is_embeddable():
            self.write_opt_predicate("[")
            self.indent()
            self.indent()
            multiple = self.write_description_body(desc)
            if multiple and (self.options.end_bnode_newline or self.options.long):
                if self.options.long:
                    self.write(" ;")
                self.writeln()
                self.dedent()
                self.write_indent()
                self.write("]")
            else:
                self.write(" ]")
                self.dedent()
            self.dedent()
            return True
        return False

    def write_list(self, list_items: List, keeplevel=False):
        items = [self.fmt.to_str(it) for it in list_items]
        width = 0
        multiline = False

        for item in items:
            width += len(item)
            if width > self.options.max_width:
                multiline = True
                break

        if not multiline and any(
            isinstance(it, Description)
            and it.is_embeddable()
            and it.has_multiple_statements()
            for it in list_items
        ):
            multiline = True

        if width == 0:
            self.write_opt_predicate("()")
        elif multiline or self.options.long:
            self.write_opt_predicate("(")
            self.writeln()
            if not keeplevel:
                self.indent()
            self.indent()
            for i, ref in enumerate(list_items):
                self.write_indent()
                if isinstance(ref, Description) and ref.list_items is not None:
                    self.write_list(ref.list_items, keeplevel=True)
                    self.writeln()
                elif self.attempt_write_blank(ref):
                    self.writeln()
                else:
                    self.write_line(items[i])
            self.dedent()
            self.write_indent()
            self.write(")")
            if not keeplevel:
                self.dedent()
        else:
            self.write_opt_predicate("(")
            for i, ref in enumerate(list_items):
                self.write(" ")
                if isinstance(ref, Description) and ref.list_items is not None:
                    self.write_list(ref.list_items)
                elif not self.attempt_write_blank(ref):
                    self.write(items[i])
            self.write(" )")

    def write_opt_predicate(self, s: str) -> None:
        if self._pending_predicate:
            s = self._pending_predicate + " " + s

        if (
            self._linewidth + len(s) > self.options.max_width
            and not self._just_indented
        ):
            self.writeln()
            self.write(self._indent)
        elif self._pending_predicate and not self._just_indented:
            s = " " + s

        self._pending_predicate = None
        self._just_indented = False
        self.write(s)

    def write(self, s: str) -> None:
        self._linewidth += len(s)
        self.out.write(s)

    def write_indent(self) -> None:
        self._just_indented = True
        self.write(self._indent)

    def write_line(self, s: str) -> None:
        print(s, file=self.out)
        self._linewidth = 0

    def writeln(self) -> None:
        print(file=self.out)
        self._linewidth = 0


def pretty_print_trig(
    store: Store,
    out: TextIO,
    prefixes: dict,
    base_iri: str | None = None,
    options: TrigFormatOptions | None = None,
) -> None:
    frame = Frame(store)
    serializer = TrigSerializer(out, prefixes, base_iri, options)
    serializer.serialize(frame)


def get_options(indent, max_width, style='modern') -> TrigFormatOptions:
    return TrigFormatOptions(
        indent=indent,
        max_width=max_width,
        sparql_keywords=style != 'classic',
        long_annotation_newline=style == 'long',
        end_annotation_newline=style != 'classic',
        end_bnode_newline=style != 'classic',
        force_type_oneline=style == 'classic',
        long=style == 'long',
    )


def main() -> None:
    import argparse
    import sys
    from pathlib import Path

    def indent_char(s: str):
        if s == 't':
            return '\t'
        if s.isdecimal():
            return ' ' * int(s)
        raise argparse.ArgumentTypeError(
            f"Invalid indent value: `{s}` (must be a number or `t`)"
        )

    argp = argparse.ArgumentParser()
    argp.add_argument('-I', '--indent', type=indent_char, default='2')
    argp.add_argument('-M', '--max-width', type=int, default=88)
    argp.add_argument('-S', '--style')
    argp.add_argument('sources', metavar='SOURCE', nargs='*')
    args = argp.parse_args()

    options = get_options(args.indent, args.max_width, args.style)

    store = Store()
    base_iri: str | None = None
    prefixes: dict[str, str] = {}

    for fpath in args.sources:
        if fpath == '-':
            reader = parse(sys.stdin.buffer, format=RdfFormat.TRIG)
        else:
            file_iri = Path(fpath).absolute().as_uri()
            reader = parse(path=fpath, base_iri=file_iri)
            if not base_iri:
                base_iri = file_iri
        store.bulk_extend(reader)
        prefixes |= reader.prefixes

    if not args.sources:
        reader = parse(sys.stdin.buffer, format=RdfFormat.TRIG)
        store.bulk_extend(reader)
        base_iri = reader.base_iri
        prefixes |= reader.prefixes

    pretty_print_trig(store, sys.stdout, prefixes, base_iri, options)


if __name__ == '__main__':
    main()

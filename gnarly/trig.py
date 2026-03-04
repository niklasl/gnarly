import re
from typing import Iterator, NamedTuple, TextIO

from pyoxigraph import (BlankNode, DefaultGraph, Literal, NamedNode, Quad,
                        RdfFormat, Store, Triple, parse)

from . import (RDF_NIL_NODE, RDFNS, Description, Document, List, Node,
               Reference, Term)

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


class TrigSettings(NamedTuple):
    indent: str = '  '
    max_list_width: int = 88
    sparql_keywords: bool = True
    long: bool = False
    # dense: bool = False


class TurtleFormatter:
    prefixes: dict[str, str]
    ns_to_prefix: dict[str, str]
    base_iri: str

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

        return f'<{iri}>'

    def clean(self, v: str) -> str:
        v = v.replace('\\', '\\\\')
        v = v.replace('\r', '\\r')
        v = v.replace('\n', '\\n')  # TODO: pretty multiline
        v = v.replace('"', r'\"')
        return v

    def stringrepr(self, v: str) -> str:
        return f'"{self.clean(v)}"'

    def lname(self, v: str) -> str:
        return PNAME_LOCAL_ESC.sub(r'\\\1', v)

    def to_str(self, n: Description | Term) -> str:
        if n == RDF_NIL_NODE:
            return '()'
        match n:
            case Description():
                return self.to_str(n.subject)
            case Triple(s, p, o):
                return f'<<( {self.to_str(s)} {self.to_str(p)} {self.to_str(o)} )>>'
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
                    return v
                elif n.datatype == XSD_DOUBLE_NODE:
                    return v + 'e0'
                else:
                    v = v.replace('"', r'\"')
                    return f'{self.stringrepr(v)}^^{n.datatype}'
            case NamedNode(v):
                return self.shorten(v)
            case BlankNode(v):
                return f'_:{n.value}'


class TrigSerializer:
    out: TextIO
    fmt: TurtleFormatter
    settings: TrigSettings
    _indent: str
    _level: int
    _pending: str | None

    def __init__(
        self, out: TextIO, fmt: TurtleFormatter, settings: TrigSettings | None = None
    ):
        self.out = out
        self.fmt = fmt
        self.settings = settings or TrigSettings()
        self._level = 0
        self._update_indent()
        self._pending = None

    def indent(self):
        self._level += 1
        self._update_indent()

    def dedent(self):
        self._level -= 1
        self._update_indent()

    def _update_indent(self):
        self._indent = self.settings.indent * self._level

    def serialize(self, doc: Document) -> None:
        self.write_prelude()
        graphkey = "GRAPH " if self.settings.sparql_keywords else ""

        self.serialize_graph(doc)
        for name, doc in doc.get_named_descriptions():
            self.writeln("")
            self.writeln(graphkey + self.fmt.to_str(name) + " {")
            self.indent()
            self.serialize_graph(doc)
            self.dedent()
            self.writeln("")
            self.writeln("}")

    def serialize_graph(self, doc: Document) -> None:
        descriptions = doc.get_descriptions()
        for desc in sorted(descriptions):
            self.writeln("")
            self.write_description(desc)

    def write_prelude(self) -> None:
        if self.settings.sparql_keywords:
            pfx_decl = "PREFIX {}: <{}>"
        else:
            pfx_decl = "@prefix {}: <{}> ."
        for pfx, ns in self.fmt.prefixes.items():
            self.writeln(pfx_decl.format(pfx, ns))

    def write_description(self, desc: Description):
        is_blank = isinstance(desc.subject, BlankNode)

        pure_blank = (
            is_blank and desc.unreferenced and not desc.annotates
        )
        s_str = "[]" if pure_blank else self.fmt.to_str(desc.subject)
        if desc.list_items is not None:
            self.write_list(desc.list_items, keeplevel=True)
            s_str = ""

        reifies = list(desc.get_reifies())
        if len(reifies) > 0:
            if pure_blank:
                rs = ""
            else:
                rs = f"~ {s_str} "
            if len(reifies) > 1:
                for triple in reifies:
                    ts, tp, to = triple
                    trpl_s = self.fmt.to_str(triple)[3:-3]
                    self.write_indented_line(f'<<{trpl_s}{rs}>> .')
            else:
                trpl_s = self.fmt.to_str(reifies[0])[3:-3]
                s_str = f'<<{trpl_s}{rs}>>'

        self.write_indent()
        typerepr = self.get_typerepr(desc)
        self.write(s_str + typerepr)
        self.indent()
        self.write_predicate_objects(desc)

        if self.settings.long:
            self.write_indented_line(".")
        else:
            self.writeln(" .")
        self.dedent()

    def get_typerepr(self, desc) -> str:
        types = ", ".join(self.fmt.to_str(t) for t in desc.get_rdftypes())
        if types:
            self._pending = " ;"
            return f" a {types}"
        else:
            return ""

    def write_predicate_objects(self, desc: Description) -> None:
        predicate_objects = sorted(desc.get_regular_predicate_objects())

        prev_p: NamedNode | None = None

        for p, ref in predicate_objects:
            same_p = p == prev_p

            if same_p:
                self._pending = " ,"

            if self._pending is not None:
                self.writeln(self._pending)
                self._pending = None
                self.write_indent()
            else:
                self.write(" ")

            if same_p:
                self.write(self.settings.indent)
            else:
                self.write(self.fmt.to_str(p) + " ")

            prev_p = p

            self.write_object(ref)

            self._pending = " ;"

        self._pending = None

    def write_object(self, ref: Reference) -> None:
        if isinstance(ref.o, Description) and ref.o.list_items is not None:
            self.write_list(ref.o.list_items)
            return

        o: Description | Term | None
        if isinstance(ref.o, Description):
            o = ref.o.subject
            if self.attempt_write_blank(ref.o):
                o = None
        else:
            o = ref.o

        if o is not None:
            self.write(self.fmt.to_str(o))

        prev_named = False
        indented = False
        for annot in sorted(ref.get_annotations()):
            if prev_named:
                self.writeln("")
                if not indented:
                    self.indent()
                    self.indent()
                    indented = True
                self.write_indent()
                self.write(" ~")

            if (
                annot.unreferenced
                and annot.only_annotates_one
                and isinstance(annot.subject, BlankNode)
                and any(annot.get_regular_predicate_objects())
            ):
                typerepr = self.get_typerepr(annot)
                self.write(" {|" + typerepr)
                self.indent()
                self.write_predicate_objects(annot)
                self.write(" |}")
                self.dedent()
            else:
                if not prev_named:
                    self.write(" ~")
                self.write(f" {self.fmt.to_str(annot.subject)}")
                prev_named = True

        if indented:
            self.dedent()
            self.dedent()

    def attempt_write_blank(self, desc: object) -> bool:
        if not isinstance(desc, Description):
            return False
        if desc.is_embeddable():
            typerepr = self.get_typerepr(desc)
            self.write("[" + typerepr)
            self.indent()
            self.indent()
            self.write_predicate_objects(desc)
            self.dedent()
            if self.settings.long:
                self.write_indent()
                self.write("]")
            else:
                self.write(" ]")
            self.dedent()
            return True
        return False

    def write_list(self, list_items: List, keeplevel=False):
        items = [self.fmt.to_str(it) for it in list_items]
        width = 0
        multiline = False

        for item in items:
            width += len(item)
            if width > self.settings.max_list_width:
                multiline = True
                break

        if width == 0:
            self.write("()")
        elif multiline:
            self.writeln("(")
            if not keeplevel:
                self.indent()
            self.indent()
            for i, ref in enumerate(list_items):
                self.write_indent()
                if isinstance(ref, Description) and ref.list_items is not None:
                    self.write_list(ref.list_items, keeplevel=True)
                    self.writeln("")
                elif self.attempt_write_blank(ref):
                    self.writeln("")
                else:
                    self.writeln(items[i])
            self.dedent()
            self.write_indent()
            self.write(")")
            if not keeplevel:
                self.dedent()
        else:
            self.write("(")
            for i, ref in enumerate(list_items):
                self.write(" ")
                if isinstance(ref, Description) and ref.list_items is not None:
                    self.write_list(ref.list_items)
                elif not self.attempt_write_blank(ref):
                    self.write(items[i])
            self.write(" )")

    def write(self, s: str) -> None:
        self.out.write(s)

    def write_indent(self) -> None:
        self.write(self._indent)

    def write_indented_line(self, s) -> None:
        self.write_indent()
        self.writeln(s)

    def writeln(self, s: str) -> None:
        print(s, file=self.out)


def pretty_print_trig(
    store: Store, out: TextIO, prefixes: dict, base_iri: str | None = None
) -> None:
    doc = Document(store)
    fmt = TurtleFormatter(prefixes, None)
    serializer = TrigSerializer(out, fmt)
    serializer.serialize(doc)


def main() -> None:
    import sys

    store = Store()
    reader = parse(sys.stdin.buffer, format=RdfFormat.TRIG)
    store.bulk_extend(reader)

    pretty_print_trig(store, sys.stdout, prefixes=reader.prefixes, base_iri=None)


if __name__ == '__main__':
    main()

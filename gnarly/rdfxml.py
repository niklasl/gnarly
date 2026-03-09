import re
from typing import TextIO, cast
from xml.dom.minidom import Document, Element

from pyoxigraph import (BlankNode, Literal, NamedNode, Quad, RdfFormat, Store,
                        Triple, parse)

from . import (RDF_NIL_NODE, RDF_TYPE_NODE, RDFNS, Description, Frame, List,
               Node, Statement, Term)
from .trig import (RDF_DIRLANGSTRING_NODE, RDF_LANGSTRING_NODE,
                   XSD_STRING_NODE, XSDNS, TurtleFormatter)

NAME_START_CHAR = fr'(?:[A-Z]|_|[a-z]|[\u00C0-\u00D6]|[\u00D8-\u00F6]|[\u00F8-\u02FF]|[\u0370-\u037D]|[\u037F-\u1FFF]|[\u200C-\u200D]|[\u2070-\u218F]|[\u2C00-\u2FEF]|[\u3001-\uD7FF]|[\uF900-\uFDCF]|[\uFDF0-\uFFFD])'  # Missing: ...|[#x10000-#xEFFFF])
QNAME_RE = re.compile(
    fr'({NAME_START_CHAR}(?:{NAME_START_CHAR}|-|\.|[0-9]|\u00B7|[\u0300-\u036F]|[\u203F-\u2040])*)$'
)


class RdfXmlSerializer:

    def __init__(self, out: TextIO, prefixes: dict, base_iri: str | None = None):
        self.fmt = TurtleFormatter(prefixes, base_iri)
        self.out = out

    def serialize(self, store: Store) -> None:
        doc = Document()

        root = doc.createElement('rdf:RDF')
        doc.appendChild(root)

        self.declare_prelude(root)

        frame = Frame(store)
        descriptions = frame.get_descriptions()
        for desc in sorted(descriptions):
            # NOTE: list subjects are unsupported in RDF/XML list syntax
            if desc.list_items is not None:
                desc.list_items = None
            self.describe(root, desc)

        print(doc.toprettyxml(indent="  "), end='', file=self.out)

    def declare_prelude(self, elem: Element) -> None:
        has_rdf_pfx = False

        if b := self.fmt.base_iri:
            elem.setAttribute("xml:base", b)

        for key, dfn in self.fmt.prefixes.items():
            if key == "rdf":
                if dfn != RDFNS:
                    # TODO: use generated new prefix instead!
                    raise ValueError(
                        f"The rdf prefix must be bound to <{RDFNS}>, not <{dfn}>"
                    )
                has_rdf_pfx = True
            if key:
                elem.setAttributeNS("xmlns", f"xmlns:{key}", dfn)
            else:
                elem.setAttributeNS("xmlns", "xmlns", dfn)

        if not has_rdf_pfx:
            elem.setAttributeNS("xmlns", f"xmlns:rdf", RDFNS)

    def create_element(self, doc: Document, v: str) -> Element:
        m = QNAME_RE.search(v)
        if m is None:
            raise ValueError(f"Cannot create element name from {v}")

        ns = v[: (m.span()[0])]
        lname = m.group(0)
        if ns in self.fmt.ns_to_prefix:
            pfx = self.fmt.ns_to_prefix[ns]
            qname = f"{pfx}:{lname}" if pfx != '' else lname
            elem = doc.createElement(qname)
        else:
            elem = doc.createElementNS(ns, lname)
            elem.setAttributeNS("xmlns", "xmlns", ns)
        return elem

    def describe(self, parent: Element, desc: Description, keep_blank_id=False) -> None:
        doc = parent.ownerDocument
        assert doc is not None
        assert doc.documentElement is not None

        d_elem = None
        rtypes = sorted(desc.get_simple_types())
        if rtypes:
            rtype = rtypes.pop(0)
            match rtype.subject:
                case NamedNode(v):
                    d_elem = self.create_element(doc, v)
                case _:
                    rtypes.insert(0, rtype)

        if d_elem is None:
            d_elem = doc.createElement("rdf:Description")

        for rtype in rtypes:
            t_elem = doc.createElement("rdf:type")
            match rtype.subject:
                case NamedNode(v):
                    self.set_id(t_elem, v, "rdf:resource")
                case BlankNode(v):
                    self.set_id(t_elem, v, "rdf:nodeID")
            d_elem.appendChild(t_elem)

        reifies = list(desc.get_reifies())
        if reifies:
            for triple in reifies:
                rp_elem = doc.createElement("rdf:reifies")
                self.describe_object(rp_elem, triple)
                d_elem.appendChild(rp_elem)

        match desc.subject:
            case NamedNode(v):
                if self.fmt.base_iri and v.startswith(self.fmt.base_iri):
                    v = v[len(self.fmt.base_iri) :]
                self.set_id(d_elem, v)
            case BlankNode(v):
                if keep_blank_id or parent is doc.documentElement:
                    self.set_id(d_elem, v, "rdf:nodeID")

        parent.appendChild(d_elem)

        for p, stmt in sorted(desc.get_regular_statements()):
            annotations = sorted(stmt.get_annotations())

            p_elem = self.create_element(doc, p.value)
            self.describe_object(p_elem, stmt.o, len(annotations) > 1)

            if (
                len(annotations) > 1
                and isinstance(stmt.o, Description)
                and isinstance(stmt.o.subject, BlankNode)
            ):
                self.describe(doc.documentElement, stmt.o, True)

            d_elem.appendChild(p_elem)

            for i, annot in enumerate(annotations):
                if i > 0:
                    p_elem = self.create_element(doc, p.value)
                    self.describe_object(p_elem, stmt.o, True)
                    d_elem.appendChild(p_elem)

                if annot.is_embeddable_annotation():
                    self.describe(doc.documentElement, annot, True)

                match annot.subject:
                    case NamedNode(v):
                        p_elem.setAttribute("rdf:annotation", v)
                    case BlankNode(v):
                        p_elem.setAttribute("rdf:annotationNodeID", v)

    def set_id(self, d_elem: Element, s: str, attr="rdf:about") -> None:
        d_elem.setAttribute(attr, s)

    def describe_object(
        self, p_elem: Element, n: Description | Term, force_ref=False
    ) -> None:
        doc = p_elem.ownerDocument
        assert doc is not None

        if isinstance(n, Description):
            # NOTE: literals are unsupported in RDF/XML list syntax
            if n.list_items is not None:
                if any(isinstance(x, Literal) for x in n.list_items):
                    n.list_items = None

            if n.list_items is not None:
                p_elem.setAttribute("rdf:parseType", "Collection")
                for item in n.list_items:
                    if isinstance(item, Description):
                        # NOTE: nested lists are unsupported in RDF/XML list syntax
                        if item.list_items is not None:
                            item.list_items = None

                        if item.is_embeddable():
                            self.describe(p_elem, item)
                        else:
                            d_elem = doc.createElement("rdf:Description")
                            p_elem.appendChild(d_elem)
                            self.describe_object(d_elem, item)
                return
            elif n.is_embeddable() and not force_ref:
                self.describe(p_elem, n)
                return

            n = n.subject

        match n:
            case NamedNode(v):
                self.set_id(p_elem, v, "rdf:resource")
                return

            case BlankNode(v):
                self.set_id(p_elem, v, "rdf:nodeID")
                return

            case Literal(_):
                v = n.value
                if n.datatype == RDF_DIRLANGSTRING_NODE:
                    self.set_text(p_elem, str(v))
                    if n.language:
                        p_elem.setAttribute("xml:lang", n.language)
                    if n.direction:
                        p_elem.setAttribute("its:dir", n.direction.value)
                    return
                elif n.datatype == RDF_LANGSTRING_NODE:
                    self.set_text(p_elem, v)
                    if n.language:
                        p_elem.setAttribute("xml:lang", n.language)
                    n.language
                    return
                elif n.datatype == XSD_STRING_NODE:
                    self.set_text(p_elem, v)
                    return
                else:
                    self.set_text(p_elem, n.value)
                    self.set_id(p_elem, n.datatype.value, "rdf:datatype")

            case Triple() as triple:
                p_elem.setAttribute("rdf:parseType", "Triple")
                t_store = Store()
                t_store.add(Quad(*triple))
                t_frame = Frame(t_store)
                t_desc = Description(t_frame, cast(Node, triple.subject))
                self.describe(p_elem, t_desc)

            case _:
                self.set_id(p_elem, XSDNS + type(n).__name__, "rdf:datatype")
                self.set_text(p_elem, repr(n))

    def set_text(self, elem: Element, text: str) -> None:
        assert elem.ownerDocument is not None
        elem.appendChild(elem.ownerDocument.createTextNode(text))


def main() -> None:
    import sys

    store = Store()
    reader = parse(sys.stdin.buffer, format=RdfFormat.TRIG)
    store.bulk_extend(reader)

    serializer = RdfXmlSerializer(
        sys.stdout, prefixes=reader.prefixes, base_iri=reader.base_iri
    )
    serializer.serialize(store)


if __name__ == '__main__':
    main()

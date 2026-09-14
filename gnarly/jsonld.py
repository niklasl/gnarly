import re
from typing import cast
from xml.dom.minidom import Document, Element

from pyoxigraph import BlankNode, Literal, NamedNode as IRI, Quad, Store, Triple

from . import (RDF_NIL, RDF_TYPE, RDF, Description, Frame, List,
               SubjectTerm, Statement, Term)
from .trig import (RDF_DIRLANGSTRING, RDF_LANGSTRING,
                   XSD_BOOLEAN, XSD_DOUBLE, XSD_INTEGER,
                   XSD_STRING, XSD, TurtleFormatter)


class JsonLdFormatter(TurtleFormatter):
    def shorten(self, iri: str) -> str:
        term = super().shorten(iri)
        return term.removeprefix('<').removesuffix('>')


class JsonLdBuilder:

    def __init__(self, prefixes: dict, base_iri: str | None = None):
        self.fmt = JsonLdFormatter(prefixes, base_iri)

    def to_data(self, frame: Frame) -> dict:
        data = {
            "@context": self.to_context(),
            "@graph": self.to_graph(frame) + self.to_named(frame),
        }
        return data

    def to_context(self):
        ctx = {}
        if self.fmt.base_iri is not None:
            ctx["@base"] = self.fmt.base_iri
        for key, dfn in self.fmt.prefixes.items():
            ctx[key or "@vocab"] = dfn

        return ctx

    def to_graph(self, frame: Frame) -> list:
        graphs = []

        descriptions = frame.get_descriptions()
        for desc in sorted(descriptions):
            graphs.append(self.describe(desc))

        return graphs

    def to_named(self, frame: Frame) -> list:
        graphs = []
        for name, nframe in frame.get_named_frames():
            named: dict = {"@id": self._to_id(name)}
            named["@graph"] = self.to_graph(nframe)
            graphs.append(named)

        return graphs

    def _to_id(self, ref: IRI | BlankNode) -> str:
        v = ref.value
        return f"_:{v}" if isinstance(ref, BlankNode) else self.fmt.shorten(v)

    def to_key(self, iri: str) -> str:
        key = self.fmt.shorten(iri)
        if key.startswith(':'):
            key = key[1:]
        return key

    def describe(self, desc: Description) -> dict:
        node: dict = {}
        rtypes = sorted(desc.get_simple_types())
        if rtypes:
            node["@type"] = [
                self.to_key(self.describe_object(rtype)["@id"]) for rtype in rtypes
            ]
        reifies = list(desc.get_reifies())

        if not (desc.is_embeddable() or desc.is_embeddable_annotation()):
            node["@id"] = self._to_id(desc.subject)

        if reifies:
            reif_data: dict = {}
            node["@reifies"] = reif_data
            for triple in reifies:
                reif_data |= self._describe_triple(triple)["@triple"]

        for p, stmt in sorted(desc.get_regular_statements()):
            key = self.to_key(p.value)

            value = self.describe_object(stmt.o)

            annotations = list(stmt.get_annotations())
            if annotations:
                value["@annotation"] = [
                    self.describe(annot) if annot.is_embeddable_annotation() else self.describe_object(annot)
                    for annot in annotations
                ]
            elif len(value) == 1 and "@value" in value:
                value = value["@value"]

            if key not in node:
                values = node[key] = []
            else:
                values = node[key]

            values.append(value)

        return node

    def describe_object(self, o: Description | Term) -> dict:
        match o:
            case Description():
                if o.list_items:
                    return {"@list": [self.describe_object(it) for it in o.list_items]}
                if o.is_embeddable():
                    return self.describe(o)
                else:
                    return self.describe_object(o.subject)
            case BlankNode(v):
                return {"@id": f"_:{v}"}
            case IRI(v):
                return {"@id": self.fmt.shorten(v)}
            case Triple(_):
                return self._describe_triple(o)
            case Literal(_):
                v = o.value
                vnode: dict[str, object] = {}
                if o.datatype == RDF_DIRLANGSTRING:
                    vnode["@value"] = str(v)
                    if o.language:
                        vnode["@language"] = o.language
                    if o.direction:
                        vnode["@direction"] = o.direction.value
                elif o.datatype == RDF_LANGSTRING:
                    vnode["@value"] = str(v)
                    if o.language:
                        vnode["@language"] = o.language
                elif o.datatype == XSD_STRING:
                    vnode["@value"] = str(v)
                elif o.datatype == XSD_BOOLEAN:
                    vnode["@value"] = v == 'true'
                elif o.datatype == XSD_INTEGER:
                    vnode["@value"] = int(v)
                elif o.datatype == XSD_DOUBLE:
                    vnode["@value"] = float(v)
                else:
                    vnode["@value"] = str(v)
                    vnode["@type"] = o.datatype.value
                return vnode

    def _describe_triple(self, triple: Triple) -> dict:
        t_store = Store()
        t_store.add(Quad(*triple))
        t_frame = Frame(t_store)
        t_desc = Description(t_frame, cast(SubjectTerm, triple.subject))
        return {"@triple": self.describe(t_desc)}

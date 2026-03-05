from typing import Iterator, cast

from pyoxigraph import (BlankNode, DefaultGraph, Literal, NamedNode, Quad,
                        QuerySolutions, Store, Triple)

RDFNS = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
RDF_TYPE = f'{RDFNS}type'
RDF_REIFIES = f'{RDFNS}reifies'
RDF_FIRST = f'{RDFNS}first'
RDF_REST = f'{RDFNS}rest'
RDF_NIL = f'{RDFNS}nil'

RDF_TYPE_NODE = NamedNode(RDF_TYPE)
RDF_REIFIES_NODE = NamedNode(RDF_REIFIES)
RDF_FIRST_NODE = NamedNode(RDF_FIRST)
RDF_REST_NODE = NamedNode(RDF_REST)
RDF_NIL_NODE = NamedNode(RDF_NIL)

LIST_PREDICATES = {RDF_FIRST_NODE, RDF_REST_NODE}
SUGAR_PREDICATES = {RDF_TYPE_NODE, RDF_REIFIES_NODE}

Node = NamedNode | BlankNode
Term = Node | Literal | Triple

type List = list[Description | Literal | Triple]

type SortKey = tuple[bool, str, int, bool, str]


class Document:
    store: Store
    name: Node | DefaultGraph

    _cache: dict[Node, Description]

    def __init__(self, store: Store, name: Node | None = None):
        self.store = store
        self.name = name or DefaultGraph()
        self._cache = {}

    def get_named_descriptions(self) -> Iterator[tuple[Node, Document]]:
        for name in self.store.named_graphs():
            yield name, Document(self.store, name)

    def get_descriptions(self) -> Iterator[Description]:
        results = self.store.query(
            'select distinct ?s { ?s ?p [] }', default_graph=self.name
        )
        for row in cast(QuerySolutions, results):
            s = row['s']
            d = self.get_description(s)
            isblank = isinstance(d.subject, BlankNode)
            if (
                (not isblank or d.unreferenced or d._astype)
                and (
                    (not isblank and not d.only_annotation_name)
                    or (isblank and not d.only_annotates_one)
                )
            ) or d.reifies or d._has_blank_cycle():
                yield d

    def get_description(self, n: Node) -> Description:
        if n in self._cache:
            return self._cache[n]

        d = Description(self, n)
        # cache lists to avoid re-generating them
        if d.list_items is not None and len(d.list_items) > 8:
            self._cache[n] = d

        return d

    def _is_asserted(self, term: Term) -> bool:
        if not isinstance(term, Triple):
            return False
        ts, tp, to = term
        return any(self.store.quads_for_pattern(ts, tp, to, self.name))

    def _check_blank_cycle(self, s: Node) -> bool:
        if not isinstance(s, BlankNode):
            return False
        referrer: BlankNode | None = s
        while referrer is not None:
            for quad in self.store.quads_for_pattern(None, None, referrer, self.name):
                if isinstance(quad.subject, BlankNode):
                    if quad.subject == s:
                        return True
                    referrer = quad.subject
                    break
                else:
                    referrer = None
            else:
                referrer = None
        return False


class Description:
    doc: Document
    subject: Node

    unreferenced: bool

    _referenced_once: bool
    _blank_cycle: bool | None
    _astype: bool

    list_items: List | None

    reifies: bool
    annotates: bool
    only_annotates: bool
    only_annotation_name: bool
    only_annotates_one: bool

    _reif_s: Node | None
    _key: SortKey

    def __init__(self, doc: Document, s: Node):
        self.doc = doc
        self.subject = s
        self._check_references()
        self._check_annotates()
        self.list_items = self._collect_list_items()
        self._key = make_sort_key(s, self._reif_s)

    def _check_references(self) -> None:
        self._blank_cycle = None
        i = 0
        for quad in self.doc.store.quads_for_pattern(
            None, None, self.subject, self.doc.name
        ):
            if i > 1:
                break
            i += 1
        self.unreferenced = i == 0
        self._referenced_once = i == 1

        self._astype = False
        for quad in self.doc.store.quads_for_pattern(
            None, RDF_TYPE_NODE, self.subject, self.doc.name
        ):
            self._astype = True
            break

    def is_embeddable(self) -> bool:
        if not isinstance(self.subject, BlankNode):
            return False
        if self.reifies or self.only_annotation_name:
            return False
        return self._referenced_once and not self._has_blank_cycle()

    def _has_blank_cycle(self) -> bool:
        if self._blank_cycle is None:
            self._blank_cycle = self._referenced_once and self.doc._check_blank_cycle(
                self.subject
            )
        return self._blank_cycle

    def _check_annotates(self) -> None:
        self.annotates = False
        self.reifies = False
        self._reif_s = None

        all_annots = True
        multiple = False
        for triple in self.get_objects(RDF_REIFIES_NODE):
            if self.annotates:
                multiple = True
            if isinstance(triple, Triple):
                if not multiple:
                    self._reif_s = cast(Node, triple.subject)
                if self.doc._is_asserted(triple):
                    self.annotates = True
                    continue
                else:
                    self.reifies = True
            all_annots = False

        self.only_annotates = self.annotates and all_annots
        self.only_annotation_name = self.only_annotates and not any(
            quad
            for quad in self.doc.store.quads_for_pattern(
                self.subject, None, None, self.doc.name
            )
            if quad.predicate != RDF_REIFIES_NODE
        )
        self.only_annotates_one = self.only_annotates and not multiple

    def _collect_list_items(self) -> List | None:
        first = None
        for o in self.get_objects(RDF_FIRST_NODE):
            if first is not None:
                return None
            first = o
        if first is None:
            return None

        rest: List | None = None
        for ro in self.get_objects(RDF_REST_NODE):
            if rest is not None:
                return None

            if not isinstance(ro, Description):
                return None

            if ro.subject == RDF_NIL_NODE:
                rest = [first]
            elif isinstance(ro.subject, BlankNode) and ro.list_items is not None:
                rest = [first] + ro.list_items

        return rest

    def get_objects(self, p: NamedNode) -> Iterator[Description | Literal | Triple]:
        for quad in self.doc.store.quads_for_pattern(
            self.subject, p, None, self.doc.name
        ):
            if isinstance(quad.object, Node):
                yield self.doc.get_description(cast(Node, quad.object))
            else:
                yield quad.object

    def get_rdftypes(self) -> Iterator[Description]:
        for quad in self.doc.store.quads_for_pattern(
            self.subject, RDF_TYPE_NODE, None, self.doc.name
        ):
            yield self.doc.get_description(cast(Node, quad.object))

    def get_reifies(self) -> Iterator[Triple]:
        for quad in self.doc.store.quads_for_pattern(
            self.subject, RDF_REIFIES_NODE, None, self.doc.name
        ):
            if isinstance(quad.object, Triple):
                if not self.doc._is_asserted(quad.object):
                    yield quad.object

    def get_regular_predicate_objects(self) -> Iterator[tuple[NamedNode, Reference]]:
        for quad in self.doc.store.quads_for_pattern(
            self.subject, None, None, self.doc.name
        ):
            if self.list_items is not None:
                if quad.predicate in LIST_PREDICATES:
                    continue

            if quad.predicate not in SUGAR_PREDICATES:
                o = (
                    self.doc.get_description(quad.object)
                    if isinstance(quad.object, Node)
                    else quad.object
                )
                reference = Reference(self, quad.predicate, o)
                yield quad.predicate, reference

    def __lt__(self, other: Description) -> bool:
        return self._key < other._key


class Reference:
    s: Description
    p: NamedNode
    o: Description | Literal | Triple
    _key: SortKey

    def __init__(self, s: Description, p: NamedNode, o: Description | Literal | Triple):
        self.s = s
        self.p = p
        self.o = o
        self._triple = Triple(
            s.subject if isinstance(s, Description) else s,
            p,
            o.subject if isinstance(o, Description) else o,
        )
        self._key = o._key if isinstance(o, Description) else make_sort_key(o)

    def get_annotations(self) -> Iterator[Description]:
        for quad in self.s.doc.store.quads_for_pattern(
            None, RDF_REIFIES_NODE, self._triple, self.s.doc.name
        ):
            yield self.s.doc.get_description(cast(Node, quad.subject))

    def __lt__(self, other: Reference) -> bool:
        return self._key < other._key


def make_sort_key(term: Term, reifies_s: Node | None = None) -> SortKey:
    isblank = isinstance(term, BlankNode) or term == RDF_NIL_NODE
    s1 = (isblank, str(term) if isinstance(term, Triple) else term.value)
    s2 = (
        (isinstance(reifies_s, BlankNode), reifies_s.value) + (1,)
        if reifies_s
        else s1 + (0,)
    )
    return s2 + s1

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

Node = NamedNode | BlankNode
Term = Node | Literal | Triple

type List = list[Description | Literal | Triple]

type SortKey = tuple[bool, str, int, bool, str]


class Frame:
    store: Store
    name: Node | DefaultGraph

    _cache: dict[Node, Description]

    def __init__(self, store: Store, name: Node | None = None):
        self.store = store
        self.name = name or DefaultGraph()
        self._cache = {}

    def get_named_descriptions(self) -> Iterator[tuple[Node, Frame]]:
        for name in self.store.named_graphs():
            yield name, Frame(self.store, name)

    def get_descriptions(self) -> Iterator[Description]:
        results = self.store.query(
            'select distinct ?s { ?s ?p [] }', default_graph=self.name
        )
        for row in cast(QuerySolutions, results):
            s = row['s']
            d = self.get_description(s)
            isblank = isinstance(d.subject, BlankNode)
            if (
                (
                    (not isblank or d.unreferenced)
                    and (
                        (not isblank and not d._only_annotation_name)
                        or (isblank and not d._only_annotates_one)
                    )
                )
                or d.reifies
                or d._has_blank_cycle()
            ):
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

    def _is_annotated(self, triple: Triple) -> bool:
        return any(self.store.quads_for_pattern(None, RDF_REIFIES_NODE, triple))

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
    frame: Frame
    subject: Node

    unreferenced: bool

    _referenced_once: bool
    _blank_cycle: bool | None

    list_items: List | None

    reifies: bool
    annotates: bool
    _only_annotates: bool
    _only_annotation_name: bool
    _only_annotates_one: bool

    _reif_s: Node | None
    _key: SortKey

    def __init__(self, frame: Frame, s: Node):
        self.frame = frame
        self.subject = s
        self._check_references()
        self._check_annotates()
        self.list_items = self._collect_list_items()
        self._key = make_sort_key(s, self._reif_s)

    def _check_references(self) -> None:
        self._blank_cycle = None
        i = 0
        for quad in self.frame.store.quads_for_pattern(
            None, None, self.subject, self.frame.name
        ):
            if i > 1:
                break
            i += 1
        self.unreferenced = i == 0
        self._referenced_once = i == 1

    def _has_blank_cycle(self) -> bool:
        if self._blank_cycle is None:
            self._blank_cycle = self._referenced_once and self.frame._check_blank_cycle(
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
                if self.frame._is_asserted(triple):
                    self.annotates = True
                    continue
                else:
                    self.reifies = True
            all_annots = False

        self._only_annotates = self.annotates and all_annots
        self._only_annotation_name = self._only_annotates and not any(
            quad
            for quad in self.frame.store.quads_for_pattern(
                self.subject, None, None, self.frame.name
            )
            if quad.predicate != RDF_REIFIES_NODE
        )
        self._only_annotates_one = self._only_annotates and not multiple

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

    def is_embeddable(self) -> bool:
        if not isinstance(self.subject, BlankNode):
            return False
        if self.reifies or self._only_annotation_name:
            return False
        return self._referenced_once and not self._has_blank_cycle()

    def is_embeddable_annotation(self) -> bool:
        return (
            self.unreferenced
            and self._only_annotates_one
            and isinstance(self.subject, BlankNode)
            and any(self.get_regular_statements())
        )

    def _triples(self, p: NamedNode | None = None) -> Iterator[Triple]:
        for quad in self.frame.store.quads_for_pattern(
            self.subject, p, None, self.frame.name
        ):
            yield quad.triple

    def get_objects(self, p: NamedNode) -> Iterator[Description | Literal | Triple]:
        for triple in self._triples(p):
            if isinstance(triple.object, Node):
                yield self.frame.get_description(cast(Node, triple.object))
            else:
                yield triple.object

    def get_simple_types(self) -> Iterator[Description]:
        for triple in self._triples(RDF_TYPE_NODE):
            if isinstance(triple.object, NamedNode) and not self.frame._is_annotated(
                triple
            ):
                yield self.frame.get_description(triple.object)

    def get_reifies(self) -> Iterator[Triple]:
        for triple in self._triples(RDF_REIFIES_NODE):
            if isinstance(triple.object, Triple):
                if not self.frame._is_asserted(triple.object):
                    yield triple.object

    def get_regular_statements(self) -> Iterator[tuple[NamedNode, Statement]]:
        for triple in self._triples(None):
            if self.list_items is not None:
                if triple.predicate in LIST_PREDICATES:
                    continue

            is_plain_rdftype = (
                triple.predicate == RDF_TYPE_NODE
                and isinstance(triple.object, NamedNode)
                and not self.frame._is_annotated(triple)
            )
            is_plain_reifies = (
                triple.predicate == RDF_REIFIES_NODE
                and isinstance(triple.object, Triple)
                and not self.frame._is_annotated(triple)
            )
            if not is_plain_rdftype and not is_plain_reifies:
                o = (
                    self.frame.get_description(triple.object)
                    if isinstance(triple.object, Node)
                    else triple.object
                )
                stmt = Statement(self, triple.predicate, o)
                yield triple.predicate, stmt

    def __lt__(self, other: Description) -> bool:
        return self._key < other._key


class Statement:
    s: Description
    p: NamedNode
    o: Description | Literal | Triple
    _triple: Triple
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
        for quad in self.s.frame.store.quads_for_pattern(
            None, RDF_REIFIES_NODE, self._triple, self.s.frame.name
        ):
            yield self.s.frame.get_description(cast(Node, quad.subject))

    def __lt__(self, other: Statement) -> bool:
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

from __future__ import annotations
from itertools import chain
from typing import Iterator, cast

from pyoxigraph import (BlankNode, DefaultGraph, Literal, NamedNode as IRI,
                        Quad, QuerySolutions, Store, Triple)

RDF = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
RDF_TYPE = IRI(f'{RDF}type')
RDF_REIFIES = IRI(f'{RDF}reifies')
RDF_FIRST = IRI(f'{RDF}first')
RDF_REST = IRI(f'{RDF}rest')
RDF_NIL = IRI(f'{RDF}nil')

LIST_PREDICATES = {RDF_FIRST, RDF_REST}

SubjectTerm = IRI | BlankNode
Term = SubjectTerm | Literal | Triple

type List = list[Description | Literal | Triple]

SortKey = tuple[bool, str, int, bool, str]


class Frame:
    store: Store
    name: SubjectTerm | DefaultGraph

    _cache: dict[SubjectTerm, Description]

    def __init__(self, store: Store, name: SubjectTerm | None = None):
        self.store = store
        self.name = name or DefaultGraph()
        self._cache = {}

    def get_named_frames(self) -> Iterator[tuple[SubjectTerm, Frame]]:
        for name in self.store.named_graphs():
            yield name, Frame(self.store, name)

    def get_descriptions(self) -> Iterator[Description]:
        results = self.store.query(
            'select distinct ?s { ?s ?p [] }', default_graph=self.name
        )
        for row in cast(QuerySolutions, results):
            s = row['s']
            d = self._get_description(s)
            if (
                not d.is_embeddable()
                and not d.is_embeddable_annotation()
                and not d._only_annotation_name
            ):
                yield d

    def _get_description(self, s: SubjectTerm) -> Description:
        if s in self._cache:
            return self._cache[s]

        d = Description(self, s)
        self._cache[s] = d

        return d

    def _is_asserted(self, term: Term) -> bool:
        if not isinstance(term, Triple):
            return False
        ts, tp, to = term
        return any(self.store.quads_for_pattern(ts, tp, to, self.name))

    def _is_annotated(self, triple: Triple) -> bool:
        return any(self.store.quads_for_pattern(None, RDF_REIFIES, triple, self.name))

    def _check_blank_cycle(self, s: SubjectTerm) -> bool:
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
    subject: SubjectTerm

    _unreferenced: bool
    _referenced_once: bool
    _blank_cycle: bool | None

    list_items: List | None

    _reifies: bool
    _reifies_multiple: bool
    _annotates: bool
    _only_annotates: bool
    _only_annotation_name: bool
    _only_annotates_one: bool

    _reif_s: SubjectTerm | None
    _key: SortKey

    def __init__(self, frame: Frame, s: SubjectTerm):
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
        self._unreferenced = i == 0
        self._referenced_once = i == 1

    def _has_blank_cycle(self) -> bool:
        if self._blank_cycle is None:
            self._blank_cycle = self._referenced_once and self.frame._check_blank_cycle(
                self.subject
            )
        return self._blank_cycle

    def _check_annotates(self) -> None:
        self._reifies = False
        self._annotates = False
        self._only_annotates = False
        self._reifies_multiple = False
        self._reif_s = None

        annot_count = 0
        reifies_count = 0
        for triple in self._get_objects(RDF_REIFIES):
            if not isinstance(triple, Triple):
                continue

            if reifies_count == 0:
                self._reif_s = cast(SubjectTerm, triple.subject)

            reifies_count += 1

            if self.frame._is_asserted(triple):
                annot_count += 1

        if reifies_count > 0:
            self._reifies = reifies_count > annot_count
            self._annotates = annot_count > 0
            self._only_annotates = annot_count == reifies_count
            self._reifies_multiple = reifies_count - annot_count > 1

        self._only_annotation_name = self._only_annotates and not any(
            quad
            for quad in self.frame.store.quads_for_pattern(
                self.subject, None, None, self.frame.name
            )
            if quad.predicate != RDF_REIFIES
        )
        self._only_annotates_one = self._only_annotates and annot_count == 1

    def _collect_list_items(self) -> List | None:
        first = None
        for o in self._get_objects(RDF_FIRST):
            if first is not None:
                return None
            first = o
        if first is None:
            return None

        rest: List | None = None
        for ro in self._get_objects(RDF_REST):
            if rest is not None:
                return None

            if not isinstance(ro, Description):
                return None

            if ro.subject == RDF_NIL:
                rest = [first]
            elif isinstance(ro.subject, BlankNode) and ro.list_items is not None:
                rest = [first] + ro.list_items

        return rest

    def is_pure_blank(self) -> bool:
        return (
            isinstance(self.subject, BlankNode)
            and self._unreferenced
            and not self._annotates
            and not self._reifies_multiple
        )

    def is_embeddable(self) -> bool:
        if not isinstance(self.subject, BlankNode):
            return False
        if self._reifies or self._only_annotation_name:
            return False
        return self._referenced_once and not self._has_blank_cycle()

    def is_embeddable_annotation(self) -> bool:
        return (
            self._unreferenced
            and self._only_annotates_one
            and isinstance(self.subject, BlankNode)
            and (any(self.get_simple_types()) or any(self.get_regular_statements()))
        )

    def has_multiple_statements(self) -> bool:
        for i, _ in enumerate(
            chain(self.get_simple_types(), self.get_regular_statements())
        ):
            if i > 0:
                return True
        return False

    def _triples(self, p: IRI | None = None) -> Iterator[Triple]:
        for quad in self.frame.store.quads_for_pattern(
            self.subject, p, None, self.frame.name
        ):
            yield quad.triple

    def _get_objects(self, p: IRI) -> Iterator[Description | Literal | Triple]:
        for triple in self._triples(p):
            if isinstance(triple.object, SubjectTerm):
                yield self.frame._get_description(cast(SubjectTerm, triple.object))
            else:
                yield triple.object

    def get_simple_types(self) -> Iterator[IRI]:
        for triple in self._triples(RDF_TYPE):
            if isinstance(triple.object, IRI) and not self.frame._is_annotated(
                triple
            ):
                yield triple.object

    def get_reifies(self) -> Iterator[Triple]:
        for triple in self._triples(RDF_REIFIES):
            if isinstance(triple.object, Triple):
                if not self.frame._is_asserted(triple.object):
                    yield triple.object

    def get_regular_statements(self) -> Iterator[tuple[IRI, Statement]]:
        for triple in self._triples(None):
            if self.list_items is not None:
                if triple.predicate in LIST_PREDICATES:
                    continue

            is_plain_rdftype = (
                triple.predicate == RDF_TYPE
                and isinstance(triple.object, IRI)
                and not self.frame._is_annotated(triple)
            )
            is_plain_reifies = (
                triple.predicate == RDF_REIFIES
                and isinstance(triple.object, Triple)
                and not self.frame._is_annotated(triple)
            )
            if not is_plain_rdftype and not is_plain_reifies:
                o = (
                    self.frame._get_description(triple.object)
                    if isinstance(triple.object, SubjectTerm)
                    else triple.object
                )
                stmt = Statement(self, triple, o)
                yield triple.predicate, stmt

    def __lt__(self, other: Description) -> bool:
        return self._key < other._key


class Statement:
    s: Description
    p: IRI
    o: Description | Literal | Triple
    _triple: Triple
    _key: SortKey

    def __init__(self, s: Description, triple: Triple, o: Description | Literal | Triple):
        self.s = s
        self.p = triple.predicate
        self.o = o
        self._triple = triple
        self._key = o._key if isinstance(o, Description) else make_sort_key(o)

    def get_annotations(self) -> Iterator[Description]:
        for quad in self.s.frame.store.quads_for_pattern(
            None, RDF_REIFIES, self._triple, self.s.frame.name
        ):
            yield self.s.frame._get_description(cast(SubjectTerm, quad.subject))

    def __lt__(self, other: Statement) -> bool:
        return self._key < other._key


def make_sort_key(term: Term, reifies_s: SubjectTerm | None = None) -> SortKey:
    isblank = isinstance(term, BlankNode) or term == RDF_NIL
    s1: tuple[bool, str] = (isblank, str(term) if isinstance(term, Triple) else term.value)
    s2: tuple[bool, str, int] = (
        (isinstance(reifies_s, BlankNode), reifies_s.value) + (1,)
        if reifies_s
        else s1 + (0,)
    )
    return s2 + s1

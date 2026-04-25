import sys
from typing import TextIO

from pyoxigraph import RdfFormat, Store, parse

from . import Frame
from .trig import TrigSerializer, TrigFormatOptions, TurtleFormatter, UCASE_KEYWORDS


def rdf_to_sparql_ask(
    store: Store, out: TextIO, prefixes: dict, base_iri: str | None = None
) -> None:
    frame = Frame(store)
    options = TrigFormatOptions(keyword_style=UCASE_KEYWORDS)
    serializer = TrigSerializer(out, prefixes, base_iri, options)
    serializer.write_prelude()
    serializer.indent()
    print(file=out)
    print("ASK WHERE {", file=out)
    serializer.write_dataset(frame)
    serializer.dedent()
    print("}", file=out)


def main() -> None:
    import sys

    store = Store()
    reader = parse(sys.stdin.buffer, format=RdfFormat.TRIG)
    store.bulk_extend(reader)

    rdf_to_sparql_ask(
        store, sys.stdout, prefixes=reader.prefixes, base_iri=reader.base_iri
    )


if __name__ == '__main__':
    main()

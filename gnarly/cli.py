import argparse
import re
import sys
from pathlib import Path

from pyoxigraph import RdfFormat, Store, Triple, parse

from . import Frame


def main() -> None:

    argp = argparse.ArgumentParser()
    argp.add_argument('-i', '--input-format', default='trig')
    argp.add_argument('-o', '--output-format', default='trig')
    argp.add_argument(
        '-b', '--base-iri', help='Set or use source as base IRI', const=True, nargs='?'
    )
    argp.add_argument('-I', '--indent', type=indent_char, default='2')
    argp.add_argument('-M', '--max-width', type=int, default=88)
    argp.add_argument('-S', '--style')
    argp.add_argument('--c14n', help='Relabel blank nodes using RDF Canonicalization', action='store_true')
    argp.add_argument('sources', metavar='SOURCE', nargs='*')
    args = argp.parse_args()

    match args.input_format:
        case "rdf":
            format = RdfFormat.RDF_XML
        case "jsonld":
            format = RdfFormat.JSON_LD
        case "nt":
            format = RdfFormat.N_TRIPLES
        case "nq":
            format = RdfFormat.N_QUADS
        case "ttl":
            format = RdfFormat.TURTLE
        case _:
            format = RdfFormat.TRIG

    store = Store()
    base_iri: str | None = None
    prefixes: dict[str, str] = {}

    for fpath in args.sources:
        if fpath == '-':
            reader = parse(sys.stdin.buffer, format=format)
        else:
            file_iri = to_absolute_iri(fpath)
            reader = parse(path=fpath, base_iri=file_iri)
            if not base_iri and args.base_iri is True:
                base_iri = file_iri
        store.bulk_extend(reader)
        if reader.base_iri is not None and args.base_iri:
            base_iri = reader.base_iri
        prefixes |= reader.prefixes

    if not args.sources:
        reader = parse(sys.stdin.buffer, format=format)
        store.bulk_extend(reader)
        base_iri = reader.base_iri
        prefixes |= reader.prefixes

    if args.c14n:
        from pyoxigraph import Dataset, CanonicalizationAlgorithm
        dataset = Dataset(store)
        dataset.canonicalize(CanonicalizationAlgorithm.RDFC_1_0)
        store = Store()
        store.extend(dataset)

    if isinstance(args.base_iri, str):
        base_iri = to_absolute_iri(args.base_iri)

    if args.output_format in {'rdf', 'rdfxml', 'xml'}:
        from .rdfxml import RdfXmlSerializer

        RdfXmlSerializer(sys.stdout, prefixes, base_iri).serialize(store)

    elif args.output_format in {'jsonld', 'json-ld', 'json'}:
        import json
        from .jsonld import JsonLdBuilder

        builder = JsonLdBuilder(prefixes=prefixes, base_iri=base_iri)
        data = builder.to_data(Frame(store))
        json.dump(data, sys.stdout, indent=2)

    elif args.output_format in {'trig', 'ttl', 'turtle'}:
        from .trig import TrigSerializer, get_options

        options = get_options(args.indent, args.max_width, args.style or "modern")

        TrigSerializer(
            sys.stdout, prefixes, base_iri, options=options
        ).serialize(Frame(store))

    else:
        from pyoxigraph import serialize

        match args.output_format:
            case "nt":
                fmt = RdfFormat.N_TRIPLES
            case "nq":
                fmt = RdfFormat.N_QUADS

        serialize(store, sys.stdout.buffer, fmt)


def indent_char(s: str):
    if s == 't':
        return '\t'
    if s.isdecimal():
        return ' ' * int(s)
    raise argparse.ArgumentTypeError(
        f"Invalid indent value: `{s}` (must be a number or `t`)"
    )


def to_absolute_iri(s: str) -> str:
    if re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', s):
        return s

    path = Path(s)
    return path.absolute().as_uri()


if __name__ == '__main__':
    main()

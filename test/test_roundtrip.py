import sys
from io import StringIO
from pathlib import Path
from typing import IO, cast

from gnarly.rq import rdf_to_sparql_ask
from gnarly.trig import pretty_print_trig
from pyoxigraph import QueryBoolean, RdfFormat, Store, parse


def load_data(source: IO, base_iri=None) -> tuple[Store, dict]:
    store = Store()
    reader = parse(source, format=RdfFormat.TRIG, base_iri=base_iri)
    store.bulk_extend(reader)
    return store, reader.prefixes


def test_roundtrip(fpath: str) -> tuple[bool, bool]:
    path = Path(fpath)
    with path.open() as f:
        store1, prefixes = load_data(f, path.absolute().as_uri())
    read1_count = len(store1)
    print(f"Checking {fpath}  ({read1_count} triples)", end=": ")

    buffer = StringIO()
    pretty_print_trig(store1, buffer, prefixes=prefixes, base_iri=None)

    buffer.seek(0)
    store2, _ = load_data(buffer)
    read2_count = len(store2)

    count_ok = read2_count == read1_count
    matches = False
    if count_ok:
        ask_buffer = StringIO()
        rdf_to_sparql_ask(store2, ask_buffer, prefixes=prefixes)
        ask_query = ask_buffer.getvalue()
        try:
            matches = bool(cast(QueryBoolean, store1.query(ask_query)))
        except SyntaxError as e:
            pass

    if count_ok and matches:
        print(f"Round-trip OK")
    else:
        msg = (
            f"got {read2_count} triples instead of {read1_count}"
            if not count_ok
            else "data mismatch"
        )
        print(f"Round-trip FAIL ({msg})")

    return count_ok, matches


def main() -> None:
    checked = 0
    skipped = 0
    ok = 0
    samesize = 0
    mismatch = 0
    error = 0
    for fpath in sys.argv[1:]:
        if '-bad-' in fpath:
            skipped += 1
            continue

        checked += 1
        try:
            count_ok, matches = test_roundtrip(fpath)
            if count_ok:
                samesize += 1
                if matches:
                    ok += 1
                else:
                    mismatch += 1
        except SyntaxError as e:
            error += 1
            print(f"SyntaxError in {fpath}: {e}")

    okmsg = f"{ok} OK"
    okish = (
        okmsg
        if ok == samesize and mismatch == 0
        else f"{okmsg}, {samesize} same size, {mismatch} mismatched"
    )
    print(
        f"Done checking {checked} files ({okish}, {error} errors; {skipped} skipped)."
    )
    if not mismatch and not mismatch and not error:
        print("All tests passed!")


if __name__ == '__main__':
    main()

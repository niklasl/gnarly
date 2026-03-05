import sys
from io import StringIO
from pathlib import Path
from typing import IO

from gnarly.trig import pretty_print_trig
from pyoxigraph import RdfFormat, Store, parse


def load_data(source: IO, base_iri=None) -> tuple[Store, dict]:
    store = Store()
    reader = parse(source, format=RdfFormat.TRIG, base_iri=base_iri)
    store.bulk_extend(reader)
    return store, reader.prefixes


def test_roundtrip(fpath: str) -> bool:
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

    ok = read2_count == read1_count
    if ok:
        print(f"Round-trip OK")
    else:
        print(f"Round-trip FAIL (got {read2_count} triples)")

    return ok


def main() -> None:
    checked = 0
    skipped = 0
    ok = 0
    fail = 0
    error = 0
    for fpath in sys.argv[1:]:
        if '-bad-' in fpath:
            skipped += 1
            continue

        checked += 1
        try:
            if test_roundtrip(fpath):
                ok += 1
            else:
                fail += 1
        except SyntaxError as e:
            error += 1
            print(f"SyntaxError in {fpath}: {e}")

    print(f"Done ({ok} OK, {fail} failed, {error} errors; {skipped} skipped).")
    if not fail and not error:
        print("All tests passed!")


if __name__ == '__main__':
    main()

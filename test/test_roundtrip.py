import sys
from io import StringIO
from pathlib import Path
from typing import IO, cast

from gnarly.rq import rdf_to_sparql_ask
from gnarly.trig import TrigSerializer
from pyoxigraph import (BlankNode, CanonicalizationAlgorithm, Dataset,
                        QueryBoolean, RdfFormat, Store, parse)


def test_roundtrip(fpath: str) -> tuple[bool, int, int]:
    store1, prefixes = _load(fpath)

    read1_count = len(store1)
    print(f"Checking {fpath}  ({read1_count} triples)", end=": ")

    buffer = StringIO()
    TrigSerializer(buffer, prefixes=prefixes, base_iri=None).serialize(store1)

    buffer.seek(0)
    store2, _ = _load_data(buffer)
    read2_count = len(store2)

    matches = False
    if read2_count == read1_count:
        dataset1 = Dataset(store1)
        dataset1.canonicalize(CanonicalizationAlgorithm.RDFC_1_0)
        dataset2 = Dataset(store2)
        dataset2.canonicalize(CanonicalizationAlgorithm.RDFC_1_0)
        matches = dataset1 == dataset2

    return matches, read1_count, read2_count


def _load(fpath: str) -> tuple[Store, dict[str, str]]:
    with (path := Path(fpath)).open() as f:
        return _load_data(f, path.absolute().as_uri())


def _load_data(source: IO, base_iri=None) -> tuple[Store, dict[str, str]]:
    store = Store()
    reader = parse(source, format=RdfFormat.TRIG, base_iri=base_iri)
    store.bulk_extend(reader)
    return store, reader.prefixes


def main() -> None:
    checked = 0
    ok = 0
    bad_ok = 0
    samesize = 0
    mismatch = 0
    differed = 0
    error = 0
    for fpath in sys.argv[1:]:
        checked += 1

        if '-bad-' in fpath:
            try:
                _load(fpath)
            except SyntaxError as e:
                bad_ok += 1
            else:
                error += 1
                print(f"Expected SyntaxError in {fpath}")
            continue

        try:
            matches, count1, count2 = test_roundtrip(fpath)
            count_ok = count2 == count1
            if count_ok and matches:
                print(f"Round-trip OK")
            else:
                msg = (
                    f"got {count2} triples instead of {count1}"
                    if not count_ok
                    else "data mismatch"
                )
                print(f"Round-trip FAIL ({msg})")

            if count_ok:
                samesize += 1
                if matches:
                    ok += 1
                else:
                    mismatch += 1
            else:
                assert not matches
                differed += 1
                print(f"FAIL (difference in {fpath})")
        except SyntaxError as e:
            error += 1
            print(f"ERROR: (SyntaxError in {fpath}: {e})")

    okcomment = f"{ok} OK, {bad_ok} expected bad" if bad_ok > 0 else f"{ok} OK"

    okmsg = f"{ok + bad_ok} Sucessful ({okcomment})"

    okish = (
        okmsg
        if ok == samesize and mismatch == 0
        else f"{okmsg}; {mismatch} same size but mismatched"
    )
    print(
        f"Done checking {checked} files ({okish}, {differed} differed, {error} errors)."
    )

    if not mismatch and not mismatch and not error:
        print("All tests passed!")
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()

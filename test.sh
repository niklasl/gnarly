#!/usr/bin/env bash
set -euo pipefail

RDF_TESTS_REPO=$1

PYTHONPATH=. python3 test/test_roundtrip.py \
  test/data/*.{ttl,trig} \
  "$RDF_TESTS_REPO"/rdf/rdf11/rdf-trig/*.trig \
  "$RDF_TESTS_REPO"/rdf/rdf12/rdf-turtle/syntax/*.ttl \
  "$RDF_TESTS_REPO"/rdf/rdf12/rdf-trig/syntax/*.trig
# TODO: fails with recursion error on long lists (e.g. the manifest)!
#  "$RDF_TESTS_REPO"/rdf/rdf11/rdf-turtle/*.ttl \

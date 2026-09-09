#!/usr/bin/env bash
set -euo pipefail

echo "Testing roundtrip of local examples:"
PYTHONPATH=. python3 test/test_roundtrip.py test/data/*.{ttl,trig}

RDF_TESTS_REPO="${1:-}"
if [[ ! -e $RDF_TESTS_REPO ]]; then
  echo "RDF tests not found in: $RDF_TESTS_REPO"
  exit 0
fi

echo "Testing roundtrip of RDF tests:"
PYTHONPATH=. python3 test/test_roundtrip.py \
  "$RDF_TESTS_REPO"/rdf/rdf11/rdf-turtle/*.ttl \
  "$RDF_TESTS_REPO"/rdf/rdf11/rdf-trig/*.trig \
  "$RDF_TESTS_REPO"/rdf/rdf12/rdf-turtle/syntax/*.ttl \
  "$RDF_TESTS_REPO"/rdf/rdf12/rdf-trig/syntax/*.trig

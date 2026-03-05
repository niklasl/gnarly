# Gnarly

Gnarly is a pretty-printer for [RDF 1.2](https://www.w3.org/TR/rdf12-concepts/), used for serializing [Turtle](https://www.w3.org/TR/rdf12-turtle/), [TriG](https://www.w3.org/TR/rdf12-trig/), and related RDF syntaxes.

Compact features:

- Uses given prefixes to prefer PNames over IRIs;
- outputs subjects with types first, then
- predicates separated by semicolon, and
- multiple objects, separated by comma; with support for
- nested blank nodes,
- compact lists (with one line per item for longer values),
- boolean keywords, pure floats and doubles, and compact triple terms;
- compact forms of reifiers (including multiple and named reifiers), and
- compact annotations on asserted triples (including multiple and named annotations);
- takes multiple references into account and avoids blank node cycles.

## Usage

Gnarly is currently written in [Python](https://www.python.org/) and uses [pyoxigraph](https://pyoxigraph.readthedocs.io/) for parsing RDF.

Command-line use:

    $ cat test/data/test-gnarly.trig | python3 -m gnarly.trig

Simple round-trip test:

    $ ./test.sh clone/of/w3c/rdf-tests  # https://github.com/w3c/rdf-tests

### Example Output

```turtle
PREFIX : <https://example.net/ns/>
PREFIX cat: <https://example.net/ns/category/>

<https://example.org/a> a :Thing ;
  :category cat:CommonThings ;
  :name "A" ;
  :references <https://example.org/b> ,
    <https://example.org/c> ;
  :value 1 ,
    "a" .

<https://example.org/b> a :Thing ;
  :category cat:CommonThings ;
  :references [ a :Thing ;
      :name "C" ] .

<https://example.org/c>
  :items ( <https://example.org/b> <https://example.org/c> ) ;
  :referenceList (
      <https://example.org/b>
      <https://example.org/c>
      <https://example.org/d>
      <https://example.org/e>
    ) ;
  :valueList ( 1 "a" ) .

<https://example.org/d> :references <https://example.org/c> .
```

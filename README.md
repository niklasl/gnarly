# Gnarly

Gnarly is a pretty-printer for [RDF 1.2](https://www.w3.org/TR/rdf12-concepts/), used for serializing [Turtle](https://www.w3.org/TR/rdf12-turtle/), [TriG](https://www.w3.org/TR/rdf12-trig/), and related RDF syntaxes.

By default, Turtle/TriG is written with the following features:

- Uses given prefixes to compact IRIs into PNames,
- optional base IRI to shorten IRIs;
- group descriptions by subject,
- writes types first, on subject line if short enough, then
- predicates separated by semicolon, and
- multiple objects, separated by comma; with support for
- nested blank nodes,
- compact lists (with one line per item for longer values),
- boolean keywords, pure floats and doubles, and compact triple terms;
- compact forms of reifiers (including multiple and named reifiers), and
- compact annotations on asserted triples (including multiple and named annotations);
- takes multiple references into account and avoids blank node cycles.

### Example Output
```turtle
PREFIX : <https://example.net/ns/>
PREFIX ctg: <https://example.net/ns/category/>

<https://example.org/a> a :Thing ;
  :category ctg:CommonThings ;
  :name "A" ;
  :references <https://example.org/b> ,
    <https://example.org/c> ;
  :value 1 ,
    "a" .

<https://example.org/b> a :Thing ;
  :category ctg:Regular ;
  :references [ a :Thing ;
      :name "C" ;
      :references [
          :category ctg:Special ;
          :name "D" ;
          :references [ :name "E" ]
        ]
    ] .

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
## Usage

Gnarly is currently written in [Python](https://www.python.org/) and uses [pyoxigraph](https://pyoxigraph.readthedocs.io/) for parsing RDF.

Command-line use:

    $ cat test/data/test-gnarly.trig | python3 -m gnarly.trig

Simple round-trip run of the official RDF turtle/trig tests:

    $ ./test.sh clone/of/w3c/rdf-tests  # from <https://github.com/w3c/rdf-tests>

## Detailed Formatting

The following examples are serialized using the default formatting options. (Many are variations on examples in the main [RDF 1.2 Primer](https://www.w3.org/TR/rdf12-primer/).)

`#` Prefixes are sorted, and declared using SPARQL-style syntax by default:
```turtle
PREFIX : <http://example.net/ns/>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
PREFIX lio: <http://purl.org/net/lio#>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
```
`#` Types are written on the subject line:
```turtle
<http://example.org/bob#me> a foaf:Person ;
  foaf:birthday "1990-07-04"^^xsd:date ;
  foaf:knows <http://example.org/alice#me> .
```
`#` Multiple triples are written under the subject:
```turtle
wd:Q12418
  dcterms:creator <http://dbpedia.org/resource/Leonardo_da_Vinci> ;
  dcterms:title "Mona Lisa" .
```
`#` Single statements and simple embedded blank nodes are kept on one line:
```turtle
wd:Q12418 dcterms:creator <http://dbpedia.org/resource/Leonardo_da_Vinci> .

wd:Q12418 lio:shows [ a <http://dbpedia.org/resource/Cypress> ] .
```
`#` Long lines also result in line breaks:
```turtle
<http://data.europeana.eu/item/04802/243FA8618938F4117025F17A8B813C5F9AA4D619>
  dcterms:subject wd:Q12418 .

<http://dbpedia.org/resource/Mona_Lisa> lio:shows [
      a <http://dbpedia.org/resource/Cypress> ] .
```
`#` A single blank annotation is written as:
```turtle
<http://example.org/bob#me> a foaf:Person ;
  foaf:topic_interest wd:Q12418 {| a rdf:Statement ;
        dcterms:creator <http://example.org/alice#me> ;
        dcterms:date "2004-01-12"^^xsd:date
      |} .
```
`#` and a named annotation like:
```turtle
<http://example.org/bob#me> a foaf:Person ;
  foaf:topic_interest wd:Q12418 ~ <http://example.org/alice#claim-1> .
```
`#` Multiple annotations are written beneath the statement:
```turtle
<http://example.org/bob#me> a foaf:Person ;
  foaf:topic_interest wd:Q12418
      {| a rdf:Statement ;
        dcterms:creator <http://example.org/alice#me> ;
        dcterms:date "2004-01-12"^^xsd:date
      |}
      {| a prov:Influence ;
        dcterms:date "1998-10-04"^^xsd:date
      |} .
```
`#` As are multiple named annotations:
```turtle
<http://example.org/bob#me> a foaf:Person ;
  foaf:topic_interest wd:Q12418
      ~ <http://example.org/alice#claim-1>
      ~ <http://example.org/bob#interest-1> .

<http://example.org/alice#claim-1> a rdf:Statement ;
  dcterms:creator <http://example.org/alice#me> ;
  dcterms:date "2004-01-12"^^xsd:date .

<http://example.org/bob#interest-1> a prov:Influence ;
  dcterms:date "1998-10-04"^^xsd:date .
```
`#` As shown in the example output above, lists are written on one or multiple lines, depending on resulting width:
```turtle
<https://example.org/c>
  :items ( <https://example.org/b> <https://example.org/c> ) ;
  :referenceList (
      <https://example.org/b>
      <https://example.org/c>
      <https://example.org/d>
      <https://example.org/e>
    ) ;
  :valueList ( 1 "a" [ :value "b" ] ) .
```

## Formatting Options

There are different style conventions for Turtle/TriG. Gnarly has options to tweak some things to adhere to different preferences.

The default settings are:
- Indent: 2 spaces
- Max column: 88 characters

There are three named styles, exemplified here with differences in output:

### Modern

This is the default, described above.
```turtle
PREFIX : <https://example.net/ns/>

<https://example.org/a> a :Thing ;
  :references <https://example.org/b> ,
    [ a :Thing ;
      :name "C" ;
      :references [
          :name "D" ;
          :references [ :name "E" ]
        ]
    ] ;
  :value 1 ,
    "a" .
```

### Classic

This form is more compact, but at the expense of readability for deeply nested blank nodes, and/or annotations. It also uses the classic, `@`-sigil for prefix and base.
```turtle
@prefix : <https://example.net/ns/> .

<https://example.org/a> a :Thing ;
  :references <https://example.org/b> ,
    [ a :Thing ;
      :name "C" ;
      :references [
          :name "D" ;
          :references [ :name "E" ] ] ] ;
  :value 1 ,
    "a" .
```

### Long

Puts predicates, including types, on new lines, and ends all statement lines with semicolon; ending a subject description with a period on its own line.

This style is useful for rapid copy&paste editing and line-based diffs:
```turtle
PREFIX : <https://example.net/ns/>

<https://example.org/a>
  a :Thing ;
  :references <https://example.org/b> ;
  :references [
      a :Thing ;
      :name "C" ;
      :references [
          :name "D" ;
          :references [ :name "E" ] ;
        ] ;
    ] ;
  :value 1 ;
  :value "a" ;
.
```

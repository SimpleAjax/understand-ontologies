"""Validate source traceability and key domain boundaries, not legal correctness."""
import hashlib
import json
from pathlib import Path
from rdflib import Graph, Namespace, RDF, RDFS, URIRef

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'ontology/domain/precheck-v1'
D=Namespace('https://cimulink.local/ontology/distribution/1#')
E=Namespace('https://cimulink.local/agreements/precheck/1#')
g=Graph().parse(FOLDER/'agreement.ttl')
source=ROOT/str(g.value(E.Document,D.sourcePath))
text=source.read_text(encoding='utf-8')
assert hashlib.sha256(source.read_bytes()).hexdigest()==str(g.value(E.Document,D.sha256))
passages=list(g.subjects(D.exactText,None))
for p in passages:
    a,b=int(g.value(p,D.startChar)),int(g.value(p,D.endChar))
    assert 0<=a<b<=len(text) and text[a:b]==str(g.value(p,D.exactText)),p
assert sorted(int(g.value(c,D.clauseNumber)) for c in g.subjects(RDF.type,D.Clause))==list(range(1,19))
provisions=list(g.objects(E.Agreement,D.hasProvision))
for p in provisions:
    assert list(g.objects(p,D.supportedBy)),p
    assert g.value(p,D.actor) and g.value(p,D.target) and g.value(p,D.action),p
    assert (p,D.withinAgreement,E.Agreement) in g,p
for s,p,o in g:
    if isinstance(o,URIRef) and str(o).startswith(str(E)):
        assert list(g.triples((o,None,None))),('Dangling local node',o)
assert (E.EarlyTerminationRight,D.actor,E.EitherParty) in g
assert (E.Modification,D.actor,E.BothParties) in g
assert (E.CompetingProductRestriction,D.exception,E.PrincipalAcceptance) in g
assert (E.PaymentUponShipment,D.actor,E.UnspecifiedPaymentActor) in g
assert not list(g.objects(E.Discount,D.percentage))
assert not list(g.subjects(RDF.type,D.ActualOrder))
# Exercise a real graph query: retrieve conditional post-termination permissions and original evidence.
rows=list(g.query('''PREFIX d: <https://cimulink.local/ontology/distribution/1#>
PREFIX ex: <https://cimulink.local/agreements/precheck/1#>
SELECT ?right ?condition ?quote WHERE {
 ex:Agreement d:hasProvision ?right .
 ?right a d:Permission ; d:actor ex:PreCheck ; d:appliesAfter ex:Termination ;
        d:condition ?condition ; d:supportedBy ?clause .
 ?clause d:exactText ?quote .
}'''))
assert len(rows)==1 and rows[0][0]==E.PostTerminationOrders and rows[0][1]==E.AcceptedBeforeTermination
report=dict(passed=True,triples=len(g),numbered_clauses=18,source_passages=len(passages),provisions=len(provisions),
    checks=['Turtle parses','source SHA matches','all source offsets match exact text','all 18 clauses present',
            'all provisions have actor/action/target/evidence','no dangling local references',
            'either-party versus joint-party distinction','competition exception retained',
            'unreadable percentage not invented','unknown payment actor retained','no actual orders invented',
            'post-termination SPARQL query returns clause 11 and acceptance condition'],
    limitation='Structural/source validation only. No domain-expert legal review or completeness proof.')
(FOLDER/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))

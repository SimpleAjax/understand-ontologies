"""Materialize the manually curated section-10 sample; not an automated extractor.

Run without arguments to write Turtle; --check validates the existing file only.
Source offsets use Python UTF-8 read_text (universal newline handling), like RAG.
"""
import argparse
import os
import hashlib
from pathlib import Path

from rdflib import Graph, Literal, Namespace, RDF, RDFS, OWL, XSD

ROOT = Path(os.environ['LAB_PROJECT_ROOT']).resolve()
OUTPUT = ROOT / 'ontology/v0.1/five-contracts.ttl'
O = Namespace('https://cimulink.local/ontology/contract-terms/0.1#')
E = Namespace('https://cimulink.local/ontology/examples/')
DOCS = {
    10: 'cuad/EuromediaHoldingsCorp_20070215_10SB12G_EX-10.B(01)_525118_EX-10.B(01)_Content License Agreement.txt',
    30: 'cuad/GopageCorp_20140221_10-K_EX-10.1_8432966_EX-10.1_Content License Agreement.txt',
    129: 'cuad/EtonPharmaceuticalsInc_20191114_10-Q_EX-10.1_11893941_EX-10.1_Development Agreement.txt',
    268: 'cuad/PareteumCorp_20081001_8-K_EX-99.1_2654808_EX-99.1_Hosting Agreement.txt',
    373: 'cuad/VirtuosoSurgicalInc_20191227_1-A_EX1A-6 MAT CTRCT_11933379_EX1A-6 MAT CTRCT_License Agreement.txt',
}
RANGES = {
    'P10a': (10, 6970, 7157), 'P10b': (10, 7158, 7967),
    'P30a': (30, 17382, 17622), 'P30b': (30, 17623, 17946),
    'P129a': (129, 36378, 37648), 'P129b': (129, 37649, 38951),
    'P268a': (268, 53736, 53935), 'P268b': (268, 53937, 54349),
    'P268c': (268, 54870, 55336), 'P373a': (373, 11714, 11913),
    'P373b': (373, 11914, 12398),
}
PARTIES = {
    10: [('Rogers', 'Rogers Cable Communications Inc.'), ('EuroMedia', 'EuroMedia Holdings Corp.')],
    30: [('PSiTech', 'PSiTech Corporation'), ('Empirical', 'Empirical Ventures, Inc.')],
    129: [('Eton', 'Eton Pharmaceuticals, Inc.'), ('Aucta', 'Aucta Pharmaceuticals, Inc.')],
    268: [('TMobile', 'T-Mobile Netherlands B.V.'), ('ElephantTalk', 'Elephant Talk Communication Holding AG')],
    373: [('JHU', 'The Johns Hopkins University'), ('Virtuoso', 'Virtuoso Surgical, Inc.')],
}
LINKS = {
    'has_party': ('Agreement', 'Party'), 'has_rule': ('Agreement', 'Rule'),
    'starts_from': ('Rule', 'Reference'), 'agreement_effective_from': ('Rule', 'Reference'),
    'ends_on_event': ('Rule', 'Reference'), 'subject_to': ('Rule', 'Condition'),
    'qualifies': ('Rule', 'Rule'), 'references_section': ('Rule', 'Reference'),
    'applies_within': ('Rule', 'Reference'), 'supported_by': (None, 'SourcePassage'),
    'resolved_to': ('Reference', 'SourcePassage'),
}


def source(index):
    return ROOT / 'data/corpus' / DOCS[index]


def build():
    g = Graph()
    for prefix, ns in [('ct', O), ('ex', E), ('owl', OWL), ('xsd', XSD)]:
        g.bind(prefix, ns)
    g.add((O[''], RDF.type, OWL.Ontology))
    g.add((O[''], RDFS.comment, Literal('Partial five-contract development sample. No claim of complete contract coverage or legal correctness.')))
    for name in ['Agreement', 'Party', 'Rule', 'Condition', 'Reference', 'SourcePassage']:
        g.add((O[name], RDF.type, OWL.Class))
        g.add((O[name], RDFS.label, Literal(name)))
    for name, (domain, target) in LINKS.items():
        g.add((O[name], RDF.type, OWL.ObjectProperty))
        if domain:
            g.add((O[name], RDFS.domain, O[domain]))
        g.add((O[name], RDFS.range, O[target]))
    for name in ['kind', 'description', 'duration', 'stated_end_date', 'renewal_count',
                 'termination_notice', 'notice_form', 'notice_actor', 'duration_status',
                 'notice_period_status', 'end_date_status', 'calendar_date_status',
                 'resolution_status', 'coverage', 'source_path', 'source_sha256',
                 'start_char', 'end_char', 'exact_text']:
        g.add((O[name], RDF.type, OWL.DatatypeProperty))

    def node(name, cls, label):
        n = E[name]
        g.add((n, RDF.type, O[cls]))
        g.add((n, RDFS.label, Literal(label)))
        return n

    def value(n, key, val, datatype=None):
        g.add((n, O[key], Literal(val, datatype=datatype)))

    def evidence(name, index, start, end):
        text = source(index).read_text(encoding='utf-8')
        assert 0 <= start < end <= len(text)
        n = node(name, 'SourcePassage', f'{name}: agreement {index}, characters {start}-{end}')
        for key, val in [('source_path', DOCS[index]), ('source_sha256', hashlib.sha256(source(index).read_bytes()).hexdigest()),
                         ('start_char', start), ('end_char', end), ('exact_text', text[start:end])]:
            value(n, key, val)
        return n

    for name, (index, start, end) in RANGES.items():
        evidence(name, index, start, end)
    for index, parties in PARTIES.items():
        text = source(index).read_text(encoding='utf-8')
        # Opening clauses, not question-bank labels, support the party identities.
        marker = {10: '  1. RIGHTS GRANTED', 30: '     WHEREAS,', 129: ' RECITALS',
                  268: '   WHEREAS:', 373: ' 1. BACKGROUND'}[index]
        opening = evidence(f'P{index}parties', index, 0, text.index(marker))
        agreement = node(f'A{index}', 'Agreement', ' / '.join(label for _, label in parties))
        value(agreement, 'coverage', 'PARTIAL_TERM_RENEWAL_TERMINATION_SAMPLE')
        for party_id, label in parties:
            party = node(party_id, 'Party', label)
            g.add((agreement, O.has_party, party))
            g.add((party, O.supported_by, opening))

    def ref(name, label, passage=None):
        n = node(name, 'Reference', label)
        value(n, 'resolution_status', 'PASSAGE_LINKED' if passage else 'UNRESOLVED')
        if passage:
            g.add((n, O.resolved_to, E[passage]))
        return n

    def rule(index, name, kind, passage, label):
        n = node(name, 'Rule', label)
        value(n, 'kind', kind)
        g.add((E[f'A{index}'], O.has_rule, n))
        g.add((n, O.supported_by, E[passage]))
        return n

    def condition(n, name, description, passage):
        c = node(name, 'Condition', description)
        value(c, 'description', description)
        g.add((c, O.supported_by, E[passage]))
        g.add((n, O.subject_to, c))

    def qualifies(n, *names):
        for name in names:
            g.add((n, O.qualifies, E[name]))

    n = rule(10, 'InitialTerm10', 'INITIAL_TERM', 'P10a', 'Initial term: ends 30 June 2010 unless earlier terminated')
    value(n, 'stated_end_date', '2010-06-30', XSD.date)
    g.add((n, O.starts_from, ref('EffectiveDate10', 'Effective Date (definition not resolved in this sample)')))
    condition(n, 'EarlyTermination10', 'Unless earlier terminated in accordance with the agreement.', 'P10a')
    n = rule(10, 'Renewal10', 'OPTIONAL_RENEWAL', 'P10b', 'Rogers option: two-year renewal')
    value(n, 'duration', 'P2Y', XSD.duration)
    condition(n, 'RogersOption10', 'Renewal is at Rogers option; exercise of the option is not established.', 'P10b')
    qualifies(n, 'InitialTerm10')
    n = rule(10, 'Continuation10', 'POST_EXPIRY_CONTINUATION', 'P10b', 'Conditional continuation after expiry')
    condition(n, 'ContinuedDistribution10', 'After initial or renewal expiry, no new agreement has been executed AND Rogers or permitted assigns continues distribution and exhibition on the ROD Service.', 'P10b')
    value(n, 'termination_notice', 'P60D', XSD.duration)
    value(n, 'notice_form', 'WRITTEN')
    value(n, 'notice_actor', 'EITHER_PARTY')
    qualifies(n, 'InitialTerm10', 'Renewal10')

    n = rule(30, 'InitialTerm30', 'INITIAL_TERM', 'P30a', 'Five years from Effective Date unless earlier terminated')
    value(n, 'duration', 'P5Y', XSD.duration)
    g.add((n, O.starts_from, ref('EffectiveDate30', 'Effective Date (definition not resolved in this sample)')))
    condition(n, 'EarlyTermination30', 'Unless terminated earlier under an express provision of the agreement; Section 6.2 is not modelled here.', 'P30a')
    n = rule(30, 'Renewal30', 'AUTOMATIC_RENEWAL', 'P30b', 'One additional three-year renewal unless timely non-renewal notice')
    value(n, 'duration', 'P3Y', XSD.duration)
    value(n, 'renewal_count', 1)
    condition(n, 'NonRenewal30', 'Automatic renewal unless either party gives the other written non-renewal notice at least 90 days before initial-term expiry.', 'P30b')
    qualifies(n, 'InitialTerm30')

    n = rule(129, 'Term129', 'CONDITIONAL_REFERENCED_TERM', 'P129a', 'Conditional effectiveness; ending refers to Section 11')
    value(n, 'end_date_status', 'NOT_ESTABLISHED_IN_SAMPLE')
    g.add((n, O.starts_from, ref('EffectiveDate129', 'Effective Date conditional on Section 11.1 wording', 'P129a')))
    g.add((n, O.references_section, ref('Section11_129', 'Section 11; only selected passages linked, not the complete section', 'P129a')))
    condition(n, 'Effectiveness129', 'Supply-agreement and FDA-review conditions, deadlines, proviso, and ETON waiver wording must be read together in the full source passage; satisfaction is not established.', 'P129a')
    n = rule(129, 'BreachTermination129', 'BREACH_TERMINATION', 'P129b', 'Termination for breach subject to notice and cure branches')
    condition(n, 'BreachCure129', 'Written notice; non-payment and other breaches have different 30/60-day branches and a conditional cure extension capped at 90 days. Read the full clause; this is not an executable decision rule.', 'P129b')
    g.add((n, O.references_section, ref('Section11_2_129', 'Section 11.2', 'P129b')))
    qualifies(n, 'Term129')

    n = rule(268, 'InitialTerm268', 'INITIAL_TERM', 'P268a', 'Redacted initial period from Commercial Launch Date')
    value(n, 'duration_status', 'REDACTED')
    g.add((n, O.agreement_effective_from, ref('AgreementDate268', 'Date of the Agreement (not resolved in this sample)')))
    g.add((n, O.starts_from, ref('LaunchDate268', 'Commercial Launch Date (not resolved in this sample)')))
    g.add((n, O.references_section, ref('Article18_268', 'Article 18; only Article 18.1(b) linked, other grounds not modelled', 'P268c')))
    n = rule(268, 'Renewal268', 'AUTOMATIC_RENEWAL', 'P268b', 'Consecutive extensions with redacted durations and notice periods')
    value(n, 'duration_status', 'REDACTED')
    value(n, 'notice_period_status', 'REDACTED')
    condition(n, 'Notice268', 'Automatic extensions if no termination notice is provided; periods and further negotiation wording contain redactions. Preserve the full clause.', 'P268b')
    qualifies(n, 'InitialTerm268')
    n = rule(268, 'BreachTermination268', 'BREACH_TERMINATION', 'P268c', 'Article 18.1(b) material-breach termination')
    condition(n, 'Remedy268', 'Material breach not remedied or incapable of remedy within a reasonable time, in any event within 60 Business Days of receipt of written notice. Business Days must not be treated as calendar days.', 'P268c')
    condition(n, 'PaymentExclusion268', 'For Article 18.1(b) only, failure by Elephant Talk to comply with Article 9.2 payment obligations is excluded from material breach. This is not a global exclusion from all termination grounds.', 'P268c')
    qualifies(n, 'InitialTerm268', 'Renewal268')

    n = rule(373, 'Term373', 'EVENT_BASED_TERM', 'P373a', 'Last relevant patent expiry in each country')
    value(n, 'calendar_date_status', 'REQUIRES_ADDITIONAL_PATENT_FACTS')
    g.add((n, O.starts_from, ref('EffectiveDate373', 'Effective Date (definition not resolved in this sample)')))
    g.add((n, O.ends_on_event, ref('PatentExpiry373', 'Expiry of last patent within PATENT RIGHTS in the country; patent dates not supplied')))
    g.add((n, O.applies_within, ref('Country373', 'Each country separately; country list not supplied')))
    n = rule(373, 'CompanyTermination373', 'COMPANY_TERMINATION', 'P373b', 'Company may terminate for any reason with 60 days written notice')
    value(n, 'termination_notice', 'P60D', XSD.duration)
    value(n, 'notice_form', 'WRITTEN')
    value(n, 'notice_actor', 'COMPANY_TO_JHU')
    g.add((n, O.references_section, ref('Paragraph8_1_373', 'Paragraph 8.1 notice requirements (not resolved in this sample)')))
    qualifies(n, 'Term373')
    n = rule(373, 'JHUTermination373', 'JHU_OPTIONAL_TERMINATION', 'P373b', 'JHU option to terminate after qualifying period without sales')
    condition(n, 'NoSales373', 'No sales of LICENSED PRODUCTS or LICENSED SERVICES in any four consecutive quarters after initial commercial sale; whether this occurred is not established.', 'P373b')
    qualifies(n, 'Term373')
    return g


def validate(g):
    def require(ok, message):
        if not ok:
            raise ValueError(message)

    require(len(set(g.subjects(RDF.type, O.Agreement))) == 5, 'Expected five agreements')
    rules = set(g.subjects(RDF.type, O.Rule))
    require(len(rules) == 13, 'Expected 13 sample rules')
    for n in rules:
        require(len(list(g.subjects(O.has_rule, n))) == 1, f'{n}: rule needs one agreement')
        require(len(list(g.objects(n, O.kind))) == 1, f'{n}: missing kind')
    for cls in [O.Rule, O.Condition, O.Party]:
        for n in g.subjects(RDF.type, cls):
            require(bool(list(g.objects(n, O.supported_by))), f'{n}: missing source evidence')
    for predicate, (domain, target) in LINKS.items():
        for a, b in g.subject_objects(O[predicate]):
            require((b, RDF.type, O[target]) in g, f'{predicate}: invalid target {b}')
            if domain:
                require((a, RDF.type, O[domain]) in g, f'{predicate}: invalid source {a}')
    for a, b in g.subject_objects(O.qualifies):
        require(set(g.subjects(O.has_rule, a)) == set(g.subjects(O.has_rule, b)), 'Cross-agreement qualification')
    passages = list(g.subjects(RDF.type, O.SourcePassage))
    require(len(passages) == 16, 'Expected eleven rule and five party passages')
    for n in passages:
        fields = {}
        for key in ['source_path', 'source_sha256', 'start_char', 'end_char', 'exact_text']:
            vals = list(g.objects(n, O[key]))
            require(len(vals) == 1, f'{n}: expected one {key}')
            fields[key] = vals[0].toPython()
        require(fields['source_path'] in DOCS.values(), 'Unexpected source path')
        path = ROOT / 'data/corpus' / fields['source_path']
        require(hashlib.sha256(path.read_bytes()).hexdigest() == fields['source_sha256'], 'Source hash mismatch')
        text = path.read_text(encoding='utf-8')
        a, b = fields['start_char'], fields['end_char']
        require(0 <= a < b <= len(text), 'Invalid source range')
        require(text[a:b] == fields['exact_text'], 'Source quotation mismatch')
    for n in g.subjects(O.duration_status, Literal('REDACTED')):
        require(not list(g.objects(n, O.duration)), 'Redacted duration has a numeric value')
    print(f'Validated {len(g)} triples, 5 agreements, {len(rules)} rules, {len(passages)} exact source passages.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if not args.check:
        graph = build()
        validate(graph)
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        graph.serialize(destination=OUTPUT, format='turtle')
    validate(Graph().parse(OUTPUT, format='turtle'))
    print(OUTPUT)

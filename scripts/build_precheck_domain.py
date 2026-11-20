"""Author a source-linked domain graph for C070. No benchmark or model access."""
import hashlib
import json
from pathlib import Path
import re

from rdflib import Graph, Literal, Namespace, RDF, RDFS, OWL, XSD, URIRef

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'ontology/domain/precheck-v1'
SOURCE = ROOT/'data/corpus/cuad/PrecheckHealthServicesInc_20200320_8-K_EX-99.2_12070169_EX-99.2_Distributor Agreement.txt'
D = Namespace('https://cimulink.local/ontology/distribution/1#')
E = Namespace('https://cimulink.local/agreements/precheck/1#')
g = Graph()
for prefix, ns in [('d',D),('ex',E),('owl',OWL),('rdfs',RDFS),('xsd',XSD)]:g.bind(prefix,ns)
text = SOURCE.read_text(encoding='utf-8')
source_sha = hashlib.sha256(SOURCE.read_bytes()).hexdigest()


def lit(s,p,value,datatype=None):
    g.add((s,D[p],Literal(value,datatype=datatype)))
    g.add((D[p],RDF.type,OWL.DatatypeProperty))


def link(s,p,o):
    g.add((s,D[p],o));g.add((D[p],RDF.type,OWL.ObjectProperty))


def node(id,kind,label):
    n=E[id];g.add((n,RDF.type,D[kind]));g.add((D[kind],RDF.type,OWL.Class));g.add((n,RDFS.label,Literal(label)))
    return n


document=node('Document','SourceDocument','Extracted PreCheck distributor agreement')
lit(document,'sourcePath',SOURCE.relative_to(ROOT).as_posix());lit(document,'sha256',source_sha)
lit(document,'offsetConvention','0-based, end-exclusive Unicode characters after Python UTF-8 text reading; not PDF page positions')
clauses={}
markers=list(re.finditer(r'(?<!\S)(1[0-8]|[1-9])\. (?=[A-Z])',text))
assert [int(m[1]) for m in markers]==list(range(1,19))
signatures=text.index('Intending to be legally bound')
for i,m in enumerate(markers):
    end=markers[i+1].start() if i+1<len(markers) else signatures
    n=node(f'Clause{m[1]}','Clause',f'Clause {m[1]}')
    clauses[int(m[1])]=n
    lit(n,'clauseNumber',int(m[1]),XSD.integer)
    lit(n,'startChar',m.start(),XSD.integer);lit(n,'endChar',end,XSD.integer)
    lit(n,'exactText',text[m.start():end]);link(n,'sourceDocument',document)
# Keep preamble, signatures and exhibit separately; original extracted page footers remain verbatim.
for id,label,a,b in [('Preamble','Preamble and business descriptions',0,markers[0].start()),
                     ('Signatures','Execution wording and signatories',signatures,text.index('.EXHIBIT A')),
                     ('ExhibitA','Exhibit A: product-list heading',text.index('.EXHIBIT A'),len(text))]:
    n=node(id,'SourcePassage',label);lit(n,'startChar',a,XSD.integer);lit(n,'endChar',b,XSD.integer)
    lit(n,'exactText',text[a:b]);link(n,'sourceDocument',document)


def evidence(n,*refs):
    for ref in refs:link(n,'supportedBy',clauses[ref] if isinstance(ref,int) else E[ref])


agreement=node('Agreement','Agreement','Co-Diagnostics / PreCheck Distributor Agreement')
link(agreement,'sourceDocument',document);lit(agreement,'statedAgreementDate','2020-03-19',XSD.date)
lit(agreement,'reviewStatus','ASSISTANT_AUTHORED_DRAFT_NOT_LEGAL_REVIEWED')
evidence(agreement,'Preamble')
for c in clauses.values():link(agreement,'hasClause',c)
principal=node('CoDiagnostics','Organization','Co-Diagnostics, Inc.')
distributor=node('PreCheck','Organization','PreCheck Health Services, Inc.')
for id,party,role in [('PrincipalRole',principal,'Principal'),('DistributorRole',distributor,'Distributor')]:
    n=node(id,'PartyRole',role);link(n,'roleHolder',party);link(n,'withinAgreement',agreement);evidence(n,'Preamble')
    link(agreement,'hasPartyRole',n)
either=node('EitherParty','ActorExpression','Either party independently')
both=node('BothParties','ActorExpression','Both parties jointly')
for n in (either,both):
    link(n,'member',principal);link(n,'member',distributor);link(n,'withinAgreement',agreement)
lit(either,'selectionMode','ANY_ONE');lit(both,'selectionMode','ALL')
products=node('Products','ProductScope','Products covered by this agreement; amendable list')
for id,label in [('QPCRKits','qPCR infectious disease kits'),('LogixSmart','Logix Smart COVID-19 PCR diagnostic test'),('CoDxBox','Co-Dx Box instrument')]:
    n=node(id,'ProductDescription',label);link(products,'namedProductDescription',n);evidence(n,1)
evidence(products,1,5);link(products,'describedIn',E.ExhibitA)
territory=node('Territory','TerritoryScope','Contract territory; initially Romania')
romania=node('Romania','Place','Romania');link(territory,'initialPlace',romania);evidence(territory,2)
texas=node('TexasLaw','LegalFramework','Laws of the State of Texas');evidence(texas,17)
for id,label in [('Utah','Utah'),('UnitedStates','United States of America'),('LatinAmerica','Latin America'),('Europe','Europe'),('Russia','Russia')]:
    n=node(id,'Place',label);evidence(n,'Preamble')
link(principal,'statedLocation',E.Utah);link(distributor,'statedOperatingOrPlannedRegion',E.UnitedStates)
for n in (E.LatinAmerica,E.Europe,E.Russia):link(distributor,'statedOperatingOrPlannedRegion',n)
for id,label in [('CameronGundry','Cameron Gundry'),('JustinAnderson','Justin Anderson')]:node(id,'Person',label);evidence(E[id],'Signatures')
link(E.CameronGundry,'signsFor',principal);lit(E.CameronGundry,'statedTitle','Dir. of Commercialization')
link(E.JustinAnderson,'signsFor',distributor);lit(E.JustinAnderson,'statedTitle','CEO')
for id,label in [('Customers','Potential customers'),('Representatives','Representatives or sub-distributors engaged by Distributor'),('Subsidiaries','Unnamed Distributor subsidiaries'),('Orders','Orders under this agreement'),('AcceptedOrders','Orders accepted by Principal before termination'),('SalesLeads','Sales leads'),('Permits','Necessary distribution licenses and permits'),('Policies','Principal policies'),('ApplicableLaw','Applicable local, state and federal laws, rules and regulations'),('ProductIP','Intellectual property embodied in Products'),('PriorAgreements','Prior agreements between these parties concerning this subject matter'),('HeirsSuccessors','Parties, heirs and successors'),('CompetitiveProducts','Products competitive with the covered Products')]:
    n=node(id,'GenericScope',label);lit(n,'instanceStatus','GENERIC_DESCRIPTION_NOT_A_KNOWN_TRANSACTION_OR_PERSON')
evidence(E.Customers,4);evidence(E.Representatives,8);evidence(E.Subsidiaries,'Preamble');evidence(E.Orders,4,13)
evidence(E.AcceptedOrders,11);evidence(E.SalesLeads,4);evidence(E.Permits,7);evidence(E.Policies,3)
evidence(E.ApplicableLaw,7);evidence(E.ProductIP,18);evidence(E.PriorAgreements,14);evidence(E.HeirsSuccessors,12);evidence(E.CompetitiveProducts,6)
termination=node('Termination','EventType','Early termination of this agreement; not an actual recorded termination')
shipment=node('Shipment','EventType','Shipment of ordered products; not an actual shipment')
expiry=node('Expiry','EventType','Reaching the stated agreement end date')
lit(expiry,'statedDate','2021-03-18',XSD.date);evidence(expiry,10);evidence(termination,10,11,12);evidence(shipment,11)


def condition(id,label,*refs):
    n=node(id,'Condition',label);evidence(n,*refs);return n


def rule(id,kind,actor,action,target,refs,label=None,**relations):
    n=node(id,kind,label or action)
    link(agreement,'hasProvision',n);link(n,'actor',actor);lit(n,'action',action)
    link(n,'target',target);link(n,'withinAgreement',agreement);evidence(n,*refs)
    lit(n,'reviewStatus','UNREVIEWED_INTERPRETATION')
    for p,values in relations.items():
        for value in values if isinstance(values,list) else [values]:link(n,p,value)
    return n


in_territory=condition('WithinTerritory','Activity concerns the agreement Territory',1,2)
accepted=condition('AcceptedBeforeTermination','Principal accepted the order before termination',11)
link(accepted,'constrains',E.AcceptedOrders)
notice=condition('WrittenNotice30Days','Early termination requires 30 days written notice',10)
lit(notice,'noticeDays',30,XSD.integer);lit(notice,'noticeForm','WRITTEN')
mutual=condition('MutualAgreement','Mutual agreement of the parties',5)
written_mutual=condition('MutualWrittenAgreement','Mutual written agreement to change Territory',2)
signed_change=condition('WrittenSignedChange','Change must be written and signed by the parties',14)
consent=condition('PriorWrittenConsent','Principal gives prior written consent to assignment',15)
rejection=condition('DistributorRejectsAddition','Distributor rejects a proposed product addition',5)
principal_acceptance=condition('PrincipalAcceptance','Principal accepts competing-product handling',6)
receipt=condition('RecipientAcknowledgement','Recipient acknowledges written or email communication',16)

appointment=rule('Appointment','Appointment',principal,'appoint as non-exclusive distributor',distributor,[1])
sell=rule('DistributionRight','Permission',distributor,'sell covered products',products,[1,2],condition=in_territory,territory=territory)
lit(sell,'exclusivity','NON_EXCLUSIVE');link(appointment,'establishes',sell)
rule('TerritoryChange','Permission',both,'amend Territory',territory,[2],condition=written_mutual)
rule('Promote','Obligation',distributor,'promote, market and sell with commercially reasonable efforts',products,[3],condition=in_territory)
rule('Attention','Obligation',distributor,'devote reasonably necessary time and attention',agreement,[3])
rule('FollowPolicies','Obligation',distributor,'abide by Principal policies',E.Policies,[3])
rule('PrincipalMarketing','Permission',principal,'contact and market products to potential customers',E.Customers,[4],condition=in_territory)
rule('PassLeads','Obligation',principal,'pass sales leads and orders to Distributor',distributor,[4],concerning=[E.SalesLeads,E.Orders])
rule('RemoveProducts','Permission',principal,'unilaterally remove Products from catalog',products,[5])
rule('ChangePrices','Permission',principal,'unilaterally change product prices',products,[5])
rule('AddProducts','ConditionalPermission',both,'add Products to covered product list',products,[5],condition=mutual)
rule('RejectedProductRight','Permission',principal,'market and distribute the rejected new product',products,[5],condition=rejection)
compete=rule('CompetingProductRestriction','Prohibition',distributor,'handle competing products directly or indirectly',E.CompetitiveProducts,[6],condition=in_territory,exception=principal_acceptance)
lit(compete,'temporalScope','DURING_AGREEMENT_TERM')
rule('ObtainPermits','Obligation',distributor,'obtain all necessary licenses and permits at own expense',E.Permits,[7])
rule('LawfulConduct','RepresentationAndWarranty',distributor,'conduct business in strict conformity with applicable law',E.ApplicableLaw,[7])
rule('EngageRepresentatives','Permission',distributor,'employ or engage representatives or sub-distributors',E.Representatives,[8])
rule('RepresentativePay','Obligation',distributor,'solely pay representative wages or commissions',E.Representatives,[8])
rule('NotPrincipalEmployees','StatusStatement',E.Representatives,'are not deemed employees of Principal',principal,[8])
discount=rule('Discount','Obligation',principal,'grant Distributor a discount based on Products and Prices',distributor,[9])
lit(discount,'percentageStatus','UNREADABLE_IN_SOURCE');lit(discount,'sourcePercentageText','¨%')
lit(discount,'variability','May vary with ordered product volume or promotions; no numeric value inferred')
term=rule('StatedTerm','TermProvision',both,'agreement remains in effect until stated end date unless sooner terminated',agreement,[10],endsAt=expiry,exception=termination)
end=rule('EarlyTerminationRight','Permission',either,'terminate without cause before stated end date',agreement,[10],condition=notice,producesEventType=termination)
post=rule('PostTerminationOrders','Permission',distributor,'receive accepted orders and sell the ordered Products',E.AcceptedOrders,[11],condition=accepted,appliesAfter=termination,territory=territory)
link(post,'qualifies',sell);lit(post,'interpretationNote','Explicit accepted-order continuation. Does not assert a general post-termination right to place new orders or that all other rights end.')
unknown_actor=node('UnspecifiedPaymentActor','ActorExpression','Payment actor not expressly named in clause 11 sentence')
evidence(unknown_actor,11)
pay=rule('PaymentUponShipment','PaymentProvision',unknown_actor,'payment to be made upon shipment',E.AcceptedOrders,[11],triggeredBy=shipment)
lit(pay,'payerStatus','NOT_EXPLICIT_IN_THIS_SENTENCE');lit(pay,'payeeStatus','NOT_EXPLICIT_IN_THIS_SENTENCE')
rule('NoTerminationChallenge','Prohibition',E.HeirsSuccessors,'challenge or contest termination',termination,[12],appliesAfter=termination)
rule('IndependentContractor','StatusStatement',distributor,'is an independent contractor; not Principal partner or employee',principal,[13])
rule('NoBindingAuthority','Prohibition',either,'bind the other party',agreement,[13])
order=rule('OrderAcceptance','Discretion',principal,'accept or reject submitted Distributor orders in sole discretion',E.Orders,[13])
link(accepted,'dependsOn',order)
rule('EntireAgreement','IntegrationProvision',both,'agreement supersedes prior agreements and is complete and exclusive statement on its subject matter',E.PriorAgreements,[14])
rule('NoOtherUnderstandings','Declaration',both,'no other agreements or understandings on this subject matter',agreement,[14])
change=rule('Modification','ValidityCondition',both,'modify this agreement',agreement,[14],condition=signed_change)
assignment=rule('Assignment','RestrictedPermission',distributor,'assign this agreement',agreement,[15],condition=consent)
communication=rule('OfficialCommunication','FormRequirement',either,'send official communication in writing or email acknowledged by recipient',agreement,[16],condition=receipt)
lit(communication,'allowedForms','WRITING_OR_EMAIL')
link(notice,'potentiallyRelevantProvision',communication)
lit(notice,'interpretationNote','Clause 16 may affect notice delivery; graph does not decide whether every acknowledged email satisfies clause 10 written notice.')
rule('GoverningLaw','GoverningLawProvision',both,'construe and govern agreement under Texas law without conflict-of-laws principles',texas,[17])
rule('AuthorityToContract','Representation',either,'has right to enter agreement and does not violate another agreement',agreement,[18])
rule('IPRights','Representation',principal,'owns or has rights to intellectual property embodied in Products',E.ProductIP,[18])
rule('DistributorRegistration','Representation',distributor,'Distributor or a subsidiary is or will be licensed and registered in Territory',territory,['Preamble'])

for id,label,ref in [('MissingExhibitProducts','Exhibit A product-list heading has no populated list in extracted text','ExhibitA'),('UnknownDiscount','Discount percentage is unreadable',9),('NoActualOrders','No actual orders, shipments or termination events are identified',11)]:
    n=node(id,'CoverageNote',label);evidence(n,ref);link(agreement,'hasCoverageNote',n)
for s in list(g.subjects(RDF.type,D.Condition)):
    link(s,'withinAgreement',agreement)
ontology=URIRef(str(D)[:-1]);g.add((ontology,RDF.type,OWL.Ontology))
g.add((ontology,RDFS.comment,Literal('Source-linked domain interpretation for one agreement. Not an exhaustive legal model, expert opinion, or inference engine. Generic scopes and event types do not assert actual transactions.')))
OUT.mkdir(parents=True,exist_ok=True)
target=OUT/'agreement.ttl'
g.serialize(target,format='turtle')
print(f'Wrote {target}: {len(g)} triples')

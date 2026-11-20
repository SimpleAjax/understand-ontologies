# PreCheck agreement: domain graph draft

Start with [agreement.ttl](agreement.ttl). This is a separate, assistant-authored interpretation of the Co-Diagnostics / PreCheck distributor agreement. The earlier C070 graph and benchmark experiments are unchanged.

## What to look at first

```text
Agreement
  → party roles → Co-Diagnostics / PreCheck
  → DistributionRight → Products / Territory (initially Romania)
  → EarlyTerminationRight → EitherParty / WrittenNotice30Days
  → PostTerminationOrders → AcceptedBeforeTermination
                         → appliesAfter Termination
                         → qualifies DistributionRight
                         → supportedBy Clause11
  → OrderAcceptance → Principal discretion
  → Modification → BothParties / WrittenSignedChange
```

Each provision has an actor, an action description, a target, its agreement scope and source evidence. Relation names such as `condition`, `exception`, `appliesAfter`, `triggeredBy` and `qualifies` let a query follow specific paths. `action` is currently readable text, not a universal normalized action taxonomy: arbitrary question-to-graph matching is future work.

## Coverage

The graph contains all 18 numbered clauses as exact source text, plus the preamble, execution/signature text and Exhibit A heading. Multiple structured provisions describe individual clauses where needed. It covers appointment, products, territory, marketing duties, supplier discretion, competition restrictions, permits, representatives, discount uncertainty, term/termination, accepted orders, payment timing, independent status, modification, assignment, notices, governing law and representations.

Having all clauses as text does not prove that every meaning has been formalized. Broad descriptions such as applicable laws and intellectual-property rights are represented as generic scopes, not fully expanded external legal knowledge. No clause is silently discarded from the source layer.

## Important distinctions

- Companies are separate from their Principal/Distributor roles.
- `EitherParty` means either may act independently; `BothParties` means joint participation.
- Orders and event types describe contractual possibilities; they are not fabricated real orders, shipments or termination events.
- The generic accepted-order scope carries the condition that Principal accepted the order before termination. Clause 11 is explicitly connected to general distribution rights, but no exclusive legal precedence or universal termination effect is inferred.
- The unreadable discount percentage remains unknown. Exhibit A's extracted text lacks a populated product list; this does not establish what was present in the original filing attachment.
- The payment sentence does not expressly identify payer/payee; those roles remain unknown here.
- The possible interaction between written termination notice and the official-communication clause is a labelled review question, not a conclusion that email necessarily satisfies notice requirements.
- Assertions are unreviewed interpretations. Source quotations support inspection; they do not certify legal correctness. Dates record what this historical agreement states, not current agreement status.

## Build and check

From the project root:

```powershell
.\.venv\Scripts\python.exe scripts/build_precheck_domain.py
.\.venv\Scripts\python.exe scripts/validate_precheck_domain.py
```

The builder reads only the contract text and these authored mappings, not benchmark questions or expected answers. Rebuilding replaces only this draft output. `validation.json` records parsing, quotation/offset, reference and domain-boundary checks, plus an actual SPARQL retrieval of the conditional post-termination permission and clause 11. These are not legal-review tests.

No graph database, LLM inference, embedding rebuild or retrieval pipeline integration is part of this draft.

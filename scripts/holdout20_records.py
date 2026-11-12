"""Manual source-only extraction decisions, frozen before benchmark unlock.

Markers locate original clauses; no benchmark imports, queries or gold offsets.
The schema permits readable descriptions for conditions we do not formalize.
"""


def curate(add):
    # add(document, start marker, end marker, kind, label, condition, fields, refs)
    add('H01', '7.1 Unless otherwise stated', '7.2 Either Party', 'INITIAL_TERM',
        '24-month initial term, Appendix qualification and automatic half-year extension',
        'Appendix may state otherwise; earlier termination or extension is possible. Written notice at least 60 days before period end prevents the half-year extension.',
        {'duration': 'P24M'}, [('starts_from', 'effective date', None), ('references_section', 'Appendix', None)])
    add('H01', '7.2 Either Party', '7.4 Upon termination', 'TERMINATION',
        'Material or prospective breach cancellation', 'Remediable breach requires failure to rectify within 30 days of written notice; clause 7.3 covers evident prospective breach.')
    add('H01', '7.5 After termination', '8 MISCELLANEOUS', 'POST_EXPIRY_CONTINUATION',
        'Sell-off period refers to Appendix 2', None, {}, [('references_section', 'Appendix 2 sell-off period', ('2.1 Contract start:', '3 PAYMENTS AND REPORTS TO LICENSOR'))])
    add('H01', '2.1 Contract start:', '3 PAYMENTS AND REPORTS TO LICENSOR', 'CONDITIONAL_REFERENCED_TERM',
        'Appendix dates and three-month sell-off', 'Raw start 04-01-06 and end 04-01-08 have ambiguous date order; preserve wording, do not normalize to calendar dates.')

    add('H02', '13. Renewal', '14. Miscellaneous', 'INITIAL_TERM',
        'Five-year term with automatic further five years', 'Effective on the date set forth above; renewal unless parties confirm termination in writing.',
        {'duration':'P5Y'}, [('starts_from','date set forth above',None)])
    add('H02', '10. Termination', '11. Notice', 'TERMINATION',
        'Expiry without renewal, mutual agreement, or provider termination on recipient default')
    add('H02', 'In the event that such delay in payment', "Either Party's failure to exercise", 'TERMINATION',
        'Provider may terminate for payment delay exceeding 15 days')

    add('H03', '(f) For purposes of this Agreement, "Standstill Period"', '4. Expenses.', 'INITIAL_TERM',
        'Standstill period ends at certification of 2018 annual-meeting vote',
        'This describes the standstill period, not an unconditional ending of every contract provision.', {},
        [('applies_within','Standstill Period obligations',None), ('ends_on_event','11:59 p.m. Eastern on certification date of stockholder vote at 2018 annual meeting',None)])
    add('H03', '(e) Notwithstanding anything contained', '(f) For purposes of this Agreement,', 'TERMINATION',
        'Conditional change-of-control termination of Sections 1, 2 and 3', 'Acquiring or counterparty must condition closing on termination of those sections; Company must not encourage that condition.', {},
        [('applies_within','Sections 1, 2 and 3 only',None)])
    add('H03', '7. Mutual Non-Disparagement.', '8.', 'CONDITIONAL_REFERENCED_TERM',
        'Non-disparagement obligations may end earlier on qualifying breach', 'Standstill expiry or material breach, subject to three-business-day notice/cure wording. Clause scope is mutual non-disparagement.', {},
        [('applies_within','Section 7 non-disparagement',None)])

    add('H04', 'This Limited Power of Attorney shall be revoked', 'This Limited Power of Attorney constitutes', 'INITIAL_TERM',
        'Power of attorney ends with underlying agreements or actual written revocation',
        'Automatic revocation on cancellation/termination of Services Agreement, or for a fund its advisory contract; other revocation effective only when FASC receives actual written notice.', {},
        [('ends_on_event','Underlying Services Agreement or fund advisory-contract cancellation/termination',None)])

    add('H05', '6.1 Except as provided', '6.2 Notwithstanding', 'INITIAL_TERM',
        'One year from Rig Release Date, subject to earlier ending and Sections 6.2-6.5', None,
        {'duration':'P1Y'}, [('starts_from','Rig Release Date',None),('references_section','Sections 6.2-6.5',('6.2 Notwithstanding','ARTICLE VII'))])
    add('H05', '6.2 Notwithstanding', 'ARTICLE VII', 'POST_EXPIRY_CONTINUATION',
        'Successful well, substitute drilling, operating-agreement and survival qualifications',
        'Sections 6.2-6.5 preserve conditional continuation and accrued/surviving liabilities; do not collapse them into one final end date.')
    add('H05', '3.4 If Company elects', 'ARTICLE IV', 'TERMINATION',
        'Nonparticipation in substitute well terminates subject to Sections 6.2-6.5')

    add('H06', '1.1 This Agreement shall take effect', '1.3 You warrant', 'INITIAL_TERM',
        'Employment begins 26 September 2019 and continues until notice under paragraph 11', None, {},
        [('starts_from','26 September 2019',None),('references_section','Paragraph 11',None)])
    add('H06', '11.1 Without prejudice', '11.3 The Company may', 'TERMINATION',
        'Six months written notice, subject to summary termination and payment-in-lieu rules',
        'Company may terminate forthwith by written notice and payment in lieu as qualified by paragraph 11.2; summary termination rights remain distinct.',
        {'termination_notice':'P6M','notice_form':'WRITTEN'})
    add('H06', '11.3 The Company may', '11.6 If your employment', 'TERMINATION',
        'Company Cause, employee Good Reason process, and death',
        'Preserve full Cause list, Good Reason notice/cure/process and immediate termination on death; no assertion that these events occurred.')
    add('H06', 'If at any time during the course', '2. JOB TITLE', 'TERMINATION',
        'Company may immediately end employment on loss of UK work rights')

    add('H07', 'Designated Sponsor Products with Pin Codes', 'The Charity Tunes system', 'INITIAL_TERM',
        'Promotion distribution and redemption windows',
        'Approximate distribution ends December 31, 2009; redemption may continue to March 31, 2010. These are promotion/redemption windows, not a demonstrated global contract expiry.', {},
        [('applies_within','Promotion and pin-code redemption only',None)])
    add('H07', 'In consideration of the fees paid', '9.EXPLICIT CONTENT:', 'CONDITIONAL_REFERENCED_TERM',
        'Exclusive sponsorship window', 'October 1, 2009 through March 31, 2010 is the sponsorship restriction period, not proof every contractual obligation expires then.', {},
        [('applies_within','Competitive program sponsorship restriction',None)])

    add('H08', '8. DURATION', '9. WITHDRAWAL AND RESOLUTION', 'INITIAL_TERM',
        'Signing-date term and extension durations are redacted', 'Non-renewal notice one year before natural expiry; automatic cessation on winding-up or insolvency; accrued obligations preserved.',
        {'duration_status':'REDACTED'}, [('starts_from','signing date',None)])
    add('H08', '9. WITHDRAWAL AND RESOLUTION', '10. TERMINATION', 'TERMINATION',
        'Withdrawal and express resolution grounds', 'Serious justified reasons or mutual consent; 30-day written withdrawal and listed breach/communication provisions; IP/economic clauses survive.')
    add('H08', '10. TERMINATION', '11. SENSITIVE INFORMATION', 'TERMINATION',
        'Insolvency-related termination rights', 'Preserve listed company insolvency events and 30-day dismissal qualification for involuntary proceedings.')

    add('H09', '5.Term of this Agreement', '6. Links', 'INITIAL_TERM',
        'Commences on registration approval; continues until termination', None, {},
        [('starts_from','Chase approval of Affiliate Registration Form',None),('ends_on_event','termination by either party',None)])
    add('H09', 'Chase also reserves the right', '• Manipulates', 'TERMINATION',
        'Chase termination for restricted content or unsuitable site', 'Site criteria continue in subsequent bullets; retain reference rather than assume this excerpt lists every unsuitable-site criterion.')

    add('H10', 'INITIAL TERM AND RENEWALS:', 'TERMINATION FOR CAUSE:', 'INITIAL_TERM',
        'Ten years from first public content availability; automatic three-year renewals',
        'Agreement effective at last signature, but initial term measured from first public availability. Non-renewal notice at least 60 days before end of a term.',
        {'duration':'P10Y'}, [('starts_from','first public availability of content on licensee property',None)])
    add('H10', 'TERMINATION FOR CAUSE:', 'EFFECT OF TERMINATION:', 'TERMINATION',
        'Insolvency or uncured material breach termination', 'Material breach has 30-day written cure provision; preserve full clause distinctions.')
    add('H10', 'EFFECT OF TERMINATION:', 'Initialed THE HENRY', 'POST_EXPIRY_CONTINUATION',
        'Property and confidentiality survive; revenue sharing ceases')

    add('H11', '7) Term', '8) Notices', 'INITIAL_TERM',
        'Twelve months, one further twelve-month renewal, and termination on notice',
        'Written non-renewal notice 90 days before original expiry; either party may also terminate on 90 days written notice.',
        {'duration':'P12M'}, [('starts_from','date hereof',None)])

    add('H12', '15.1 Term.', '15.2 Termination.', 'INITIAL_TERM',
        'Seven years plus automatic annual renewals', 'Earlier termination possible; non-renewal notice at least 180 days before beginning of renewal term.',
        {'duration':'P7Y'}, [('starts_from','Effective Date',None)])
    add('H12', '15.2 Termination.', '15.3 Effect of Termination.', 'TERMINATION',
        'Mutual breach/insolvency and party-specific acquisition, competition and performance grounds',
        'Some acquisition and performance values are redacted. Keep the complete source provision, including ENERGOUS convenience right after third anniversary on 180 days notice.')
    add('H12', '15.3 Effect of Termination.', '16. ESCROW.', 'POST_EXPIRY_CONTINUATION',
        'Survival, wind-down period and continuing supply obligations',
        'Redacted wind-down/end caps and customer-contract conditions prevent treating initial expiry as the end of all rights.')
    add('H12', 'If none of the foregoing alternatives', '11.4 Disclaimer.', 'TERMINATION',
        'DIALOG infringement-remedy termination', 'If preceding remedy alternatives unavailable within commercially reasonable time; prompt prior written notice.', {},
        [('references_section','Section 11.3 preceding remedy alternatives',None)])

    add('H13', 'ARTICLE VI "Termination of Agreement"', 'ARTICLE VII', 'INITIAL_TERM',
        'Written-notice termination while employee lives; automatic end on employment termination', None, {},
        [('ends_on_event','termination of Employee employment',None)])

    add('H14', 'SECTION 9. TERMINATION OF AGREEMENT.', 'SECTION 10. NOTICES.', 'CONDITIONAL_REFERENCED_TERM',
        'Agent termination grounds before Closing Time, including unconsummated offering by June 30, 2007',
        'June 30, 2007 is one conditional termination ground, not an unconditional fixed end date. Expense and indemnity survival qualifications remain.', {},
        [('references_section','Section 5 conditions',None),('applies_within','Agent termination at or before Closing Time',None)])

    add('H15', '6.1 Term.', '6.2 Termination for Cause', 'INITIAL_TERM',
        'Agreement through Delivery Period; certain licenses survive', None, {},
        [('starts_from','Effective Date',None),('ends_on_event','end of Delivery Period',('1.11 "Delivery Period"','1.12 "Display"'))])
    add('H15', '6.2 Termination for Cause', '6.4 Remedies.', 'TERMINATION',
        'Material breach, bankruptcy and termination effects', 'Material breach includes 60-day written cure period. Perpetual content licenses are unaffected as described in Section 6.3.')
    add('H15', '(ii) Scope of License. The term of the license for Translated Content', '2.4 Non-Display.', 'OPTIONAL_RENEWAL',
        'Translated-content license has redacted duration and renewal or purchase options', 'Scope is Translated Content; duration and rights differ from main agreement Delivery Period.',
        {'duration_status':'REDACTED'}, [('applies_within','Translated Content license only',None)])

    add('H16', 'VI. TERM/TERMINATION', 'B. Termination for breach', 'INITIAL_TERM',
        'Three years with automatic two-year extensions unless advised otherwise', None,
        {'duration':'P3Y'}, [('starts_from','Effective Date',None)])
    add('H16', 'B. Termination for breach', 'VII. ASSIGNMENT', 'TERMINATION',
        'Purchase failures, insolvency, cure and three-month wind-down rights', 'Preserve purchase thresholds, 30-day breach cure, immediate notice and post-termination sales/supply conditions together.')
    add('H16', 'C. Price Increase:', 'D. All payments', 'TERMINATION',
        'Termination if price-increase agreement cannot be reached', 'Parties must first attempt in good faith to agree reasonable justified price increase.')

    add('H17', '13. Termination and Payment of Expenses.', '14. Notices.', 'INITIAL_TERM',
        'Effective on date hereof, ends upon termination of Offering', None, {},
        [('starts_from','date hereof',None),('ends_on_event','termination of Offering',None)])
    add('H17', 'In the event the Company is unable to sell', 'In the event the Offering is terminated', 'TERMINATION',
        'Minimum-share sale deadline and refund condition', 'Termination if unable to sell minimum 1,875,000 shares on or before June 30, 2007; specified surviving sections remain.')
    add('H17', 'Except as otherwise provided in this Agreement, the appointment', 'In the event the Company is unable', 'CONDITIONAL_REFERENCED_TERM',
        'Agent appointment ends at completion, expiry or termination of Offering', None, {},
        [('applies_within','Agent appointment',None)])

    add('H18', 'Section 6.1 Term of Services.', 'Section 6.2 Termination of Services.', 'INITIAL_TERM',
        'Default twelve-month service terms with exhibit-specific dates', 'Each service has its own commencement/ending date; Exhibits A/B and earlier termination may override the twelve-month default.',
        {'duration':'P12M'}, [('starts_from','service-specific Commencement Date',None),('applies_within','each service separately',None)])
    add('H18', 'Section 6.3 Termination of Agreement.', 'Section 6.4 Effect of Termination.', 'TERMINATION',
        'Agreement ends when all services end, or on qualifying breach/insolvency', 'Good-faith invoice/service disputes are excluded from material breach; cure and insolvency conditions preserved.')
    add('H18', 'Section 6.2 Termination of Services.', 'Section 6.3 Termination of Agreement.', 'TERMINATION',
        'Convenience termination of services with migration-plan and cost qualifications', '30 days prior written notice subject to exhibits and Section G1 migration plan; not an unconditional agreement-wide termination right.')
    add('H18', ('All services in group 24 months from the Commencement Date', 0), 'G1.1.1 Autosys', 'CONDITIONAL_REFERENCED_TERM',
        'Exhibit G1 service-group term is twenty-four months with migration plan', None,
        {'duration':'P24M'}, [('applies_within','Exhibit A G1.1 service group',None)])

    add('H19', 'AGREEMENT PERIOD', 'PAYMENT TERMS', 'INITIAL_TERM',
        'Agreement period January 1, 2019 through December 31, 2023', None,
        {'stated_end_date':'2023-12-31'}, [('starts_from','January 1, 2019',None)])
    add('H19', 'TERMINATION Notwithstanding anything', 'TERMS AND CONDITIONS', 'TERMINATION',
        'Main agreement requires written material-breach notice and thirty-day cure', 'Expressly applies notwithstanding Attachments A, G or H; do not use conflicting attachment wording without this qualification.')
    add('H19', 'CHANGE IN CIRCUMSTANCES Notwithstanding anything', 'Promptly after any public announcement', 'TERMINATION',
        'Main-agreement change-in-circumstances termination limited by law-compliance requirement', 'Expressly notwithstanding Attachments A/G/H; other notice and defined-event requirements remain.', {},
        [('references_section','Change in Circumstances definition and notice requirements',None)])

    add('H20', '6.01. Term.', '6.02. Termination.', 'INITIAL_TERM',
        'Ends May 31, 2015 unless earlier terminated; optional two-year extension', 'Additional two-year period requires written consent of both parties; accrued obligations survive.',
        {'stated_end_date':'2015-05-31'})
    add('H20', '6.02. Termination.', 'ARTICLE VII NOTICES', 'TERMINATION',
        'Material breach, company-specific grounds and mutual consent', 'Preserve thirty-day cure and listed change-of-control, bankruptcy and other grounds; surviving obligations remain.')

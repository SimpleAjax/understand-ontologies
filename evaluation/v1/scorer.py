"""Version 1 character-overlap scorer; original upstream types are pinned externally."""
from collections import defaultdict

def score(passages, question, texts, types):
    _, GroundTruth, Retrieved, merge, QAResult = types
    grouped = defaultdict(list)
    for p in passages:
        grouped[p['file_path']].append(tuple(p['span']))
    spans = [Retrieved(file_path=path, span=span, score=0.0)
             for path, ranges in sorted(grouped.items()) for span in merge(ranges)]
    expected = []
    for s in question['snippets']:
        a, b = s['span']
        if texts[s['file_path']][a:b] != s['answer']:
            raise ValueError('Expected evidence differs from source')
        expected.append({'file_path': s['file_path'], 'span': [a, b], 'text': s['answer']})
    evaluated = QAResult(qa_gt=GroundTruth(query=question['query'], snippets=question['snippets']),
                         retrieved_snippets=spans)
    for p in passages:
        start, end = p['span']
        overlaps = merge([(max(start, e['span'][0]), min(end, e['span'][1]))
                          for e in expected if e['file_path'] == p['file_path']
                          and max(start, e['span'][0]) < min(end, e['span'][1])])
        segments, pos = [], start
        for a, b in overlaps:
            segments.extend([{'text': texts[p['file_path']][pos:a], 'relevant': False},
                             {'text': texts[p['file_path']][a:b], 'relevant': True}])
            pos = b
        segments.append({'text': texts[p['file_path']][pos:end], 'relevant': False})
        p.update(segments=segments, relevant_characters=sum(b-a for a,b in overlaps))
    return {'precision': evaluated.precision, 'recall': evaluated.recall,
            'retrieved': passages, 'expected': expected,
            'returned_characters': sum(len(p['text']) for p in passages),
            'scored_spans': [{'file_path': s.file_path, 'span': list(s.span)} for s in spans]}

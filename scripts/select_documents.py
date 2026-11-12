"""Freeze the documents and questions for our first retrieval experiment."""

import hashlib
import json
import random
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUTPUT = ROOT / "experiments" / "cuad-100"
SEED = 42


def main():
    benchmark_path = DATA / "benchmarks" / "cuad.json"
    tests = json.loads(benchmark_path.read_text(encoding="utf-8"))["tests"]
    files = sorted((DATA / "corpus" / "cuad").glob("*.txt"))
    actual_paths = {}
    for path in files:
        relative = path.relative_to(DATA / "corpus").as_posix()
        normalized = unicodedata.normalize("NFC", relative)
        assert normalized not in actual_paths, "Ambiguous normalized filename"
        actual_paths[normalized] = relative

    referenced = sorted({s["file_path"] for q in tests for s in q["snippets"]})
    paths = {p: actual_paths[unicodedata.normalize("NFC", p)] for p in referenced}
    texts = {
        p: (DATA / "corpus" / actual).read_text(encoding="utf-8")
        for p, actual in paths.items()
    }
    # Match upstream Python text reading: UTF-8 with universal newline handling.
    # Validate every CUAD expected passage, not just the selected subset.
    for question in tests:
        assert question["snippets"], "Question has no expected evidence"
        for snippet in question["snippets"]:
            text = texts[snippet["file_path"]]
            start, end = snippet["span"]
            assert 0 <= start < end <= len(text), "Invalid character positions"
            assert text[start:end] == snippet["answer"], "Expected text differs"

    selected = sorted(random.Random(SEED).sample(referenced, 100))
    selected_set = set(selected)
    questions = [
        {"source_index": index, **question}
        for index, question in enumerate(tests)
        if all(s["file_path"] in selected_set for s in question["snippets"])
    ]
    documents = []
    for source in selected:
        path = DATA / "corpus" / paths[source]
        documents.append({
            "file_path": source,
            "local_file_path": paths[source],
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "characters": len(texts[source]),
        })
    manifest = {
        "collection": "cuad",
        "seed": SEED,
        "selection": "Random sample from sorted benchmark-referenced document paths",
        "source_benchmark": "data/benchmarks/cuad.json",
        "source_benchmark_sha256": hashlib.sha256(benchmark_path.read_bytes()).hexdigest(),
        "source_document_count": len(referenced),
        "source_question_count": len(tests),
        "all_source_passages_validated": True,
        "filename_aliases": {p: a for p, a in paths.items() if p != a},
        "document_count": len(documents),
        "question_count": len(questions),
        "total_characters": sum(d["characters"] for d in documents),
        "documents": documents,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, value in [("selection.json", manifest), ("questions.json", {"tests": questions})]:
        (OUTPUT / name).write_text(json.dumps(value, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(f"Selected {len(documents)} documents and {len(questions)} questions.")
    print(f"Saved to {OUTPUT}")


if __name__ == "__main__":
    main()

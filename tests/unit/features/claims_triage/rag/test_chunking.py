import pytest

from ombuds.features.claims_triage.rag.chunking import chunk_document


def test_each_heading_section_becomes_its_own_chunk() -> None:
    text = "# Title\nIntro.\n\n## Delays\nThree hours or more.\n\n## Cancellations\nTwo weeks notice."

    chunks = chunk_document("doc.md", text)

    assert [c.content for c in chunks] == [
        "# Title\nIntro.",
        "## Delays\nThree hours or more.",
        "## Cancellations\nTwo weeks notice.",
    ]
    assert [c.chunk_index for c in chunks] == [0, 1, 2]
    assert {c.source for c in chunks} == {"doc.md"}


def test_text_before_the_first_heading_is_kept() -> None:
    chunks = chunk_document("doc.md", "Preamble.\n\n# Heading\nBody.")

    assert [c.content for c in chunks] == ["Preamble.", "# Heading\nBody."]


@pytest.mark.parametrize("text", ["", "   \n\n  "])
def test_blank_text_yields_no_chunks(text: str) -> None:
    assert chunk_document("doc.md", text) == []


def test_long_section_is_packed_by_paragraph_and_repeats_its_heading() -> None:
    paragraphs = [f"Paragraph {i} " + "x" * 40 for i in range(6)]
    text = "## Rules\n" + "\n\n".join(paragraphs)

    chunks = chunk_document("doc.md", text, max_chars=120, overlap=10)

    assert len(chunks) > 1
    assert all(c.content.startswith("## Rules\n\n") for c in chunks)
    assert all(len(c.content) <= 120 for c in chunks)
    joined = "\n".join(c.content for c in chunks)
    assert all(p in joined for p in paragraphs)


def test_single_oversized_paragraph_is_cut_with_overlap() -> None:
    paragraph = "".join(str(i % 10) for i in range(300))

    chunks = chunk_document("doc.md", paragraph, max_chars=100, overlap=20)

    assert all(len(c.content) <= 100 for c in chunks)
    for first, second in zip(chunks, chunks[1:], strict=False):
        assert first.content[-20:] == second.content[:20]
    assert chunks[-1].content.endswith(paragraph[-10:])


@pytest.mark.parametrize("length", [99, 100, 101])
def test_section_exactly_at_the_limit_stays_one_chunk(length: int) -> None:
    chunks = chunk_document("doc.md", "a" * length, max_chars=100, overlap=10)

    assert len(chunks) == (1 if length <= 100 else 2)


def test_overlap_not_smaller_than_max_chars_is_rejected() -> None:
    with pytest.raises(ValueError, match="overlap"):
        chunk_document("doc.md", "text", max_chars=50, overlap=50)

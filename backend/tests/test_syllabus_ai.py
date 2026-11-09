"""Reading a syllabus with AI: the parts that need no database or provider."""

from __future__ import annotations

import base64
import json

import pytest

from app.core.errors import ValidationFailed
from app.modules.ai.providers import Attachment, ProviderRequest, gemini
from app.modules.ai.providers import anthropic as anthropic_provider
from app.modules.library import ai_import, spreadsheet

OUTLINE = {
    "papers": ["Paper II - Geology", "Paper III - Chemistry"],
    "levels": [
        {
            "name": "Prelims (Stage I)",
            "subjects": [
                {
                    "name": "Paper II - Geology",
                    "units": [
                        {"name": "1. Mineralogy", "topics": ["Bravais lattices", "Isomorphism"]},
                        {
                            "name": "2. Stratigraphy",
                            "chapters": [
                                {"name": "Archaean", "topics": ["Dharwar craton"]},
                                {"name": "Proterozoic", "topics": []},
                            ],
                        },
                        {"name": "3. Field Work"},
                    ],
                },
                {"name": "Paper III - Chemistry", "units": []},
            ],
        }
    ],
}


def _flatten(outline=OUTLINE, *, level_hint=None):
    return ai_import.flatten(
        outline,
        track="upsc",
        level_hint=level_hint,
        medium="English",
        difficulty="Hard",
        exam_tags="upsc",
    )


def _path(row: dict[str, str]) -> tuple[str, ...]:
    return (row["subject"], row["unit"], row["chapter"], row["topic"])


def test_flatten_gives_one_row_per_topic_and_keeps_empty_branches() -> None:
    rows = _flatten()

    assert [_path(r) for r in rows] == [
        ("Paper II - Geology", "1. Mineralogy", "", "Bravais lattices"),
        ("Paper II - Geology", "1. Mineralogy", "", "Isomorphism"),
        ("Paper II - Geology", "2. Stratigraphy", "Archaean", "Dharwar craton"),
        ("Paper II - Geology", "2. Stratigraphy", "Proterozoic", ""),
        ("Paper II - Geology", "3. Field Work", "", ""),
        ("Paper III - Chemistry", "", "", ""),
    ]
    assert {r["track"] for r in rows} == {"upsc"}
    assert {r["difficulty"] for r in rows} == {"Hard"}
    # Every row is one the spreadsheet import accepts as it is.
    assert not any(row.problems for row in spreadsheet.rows_from_cells(rows))


def test_a_level_hint_names_a_single_level_only() -> None:
    assert {r["level"] for r in _flatten(level_hint="Class 10")} == {"Class 10"}

    two = {"levels": [{**OUTLINE["levels"][0]}, {**OUTLINE["levels"][0], "name": "Mains"}]}
    assert {r["level"] for r in _flatten(two, level_hint="Class 10")} == {
        "Prelims (Stage I)",
        "Mains",
    }


def test_flatten_skips_repeats_and_junk_the_model_may_return() -> None:
    outline = {
        "levels": [
            {
                "name": "Class 10",
                "subjects": [
                    {
                        "name": "Science",
                        "units": [
                            {"name": "Light", "topics": ["Reflection", "reflection ", "", 7]},
                            {"name": "", "topics": ["orphan"]},
                            "not an object",
                        ],
                    }
                ],
            },
            {"subjects": []},
        ]
    }

    assert [_path(r) for r in _flatten(outline)] == [
        ("Science", "Light", "", "Reflection"),
        ("Science", "Light", "", "7"),
    ]


def test_parse_outline_accepts_fenced_json_and_explains_a_cut_off_answer() -> None:
    fenced = "```json\n" + json.dumps(OUTLINE) + "\n```"
    assert ai_import.parse_outline(fenced)["levels"][0]["name"] == "Prelims (Stage I)"

    with pytest.raises(ValidationFailed, match="split the PDF"):
        ai_import.parse_outline(json.dumps(OUTLINE)[:-40])
    with pytest.raises(ValidationFailed, match="did not return"):
        ai_import.parse_outline('["a list"]')


def test_papers_listed_but_not_read_are_reported() -> None:
    outline = {
        "papers": ["Paper II - Geology", "Formal Writing in Hindi", "Paper III: Chemistry"],
        "levels": OUTLINE["levels"],
    }
    # Punctuation and case differences are not "missing".
    assert ai_import.missing_papers(outline) == ["Formal Writing in Hindi"]
    assert ai_import.missing_papers(OUTLINE) == []


def test_reviewed_rows_round_trip_through_excel() -> None:
    rows = _flatten()

    parsed = spreadsheet.read_rows(spreadsheet.write_rows(rows))

    assert len(parsed) == len(rows)
    assert parsed[0].path == [
        ("level", "Prelims (Stage I)"),
        ("subject", "Paper II - Geology"),
        ("unit", "1. Mineralogy"),
        ("topic", "Bravais lattices"),
    ]


def _request(**overrides) -> ProviderRequest:
    return ProviderRequest(
        model_id="gemini-3.5-flash-lite",
        system_prompt="system",
        user_text="read this",
        max_output_tokens=100,
        **overrides,
    )


def test_gemini_sends_the_file_before_the_text_and_asks_for_json() -> None:
    body = gemini.build_body(
        _request(
            attachments=(Attachment("application/pdf", b"%PDF-1.7"),),
            json_schema={"type": "object"},
        )
    )

    file_part, text_part = body["contents"][0]["parts"]
    assert file_part["inline_data"]["mime_type"] == "application/pdf"
    assert base64.b64decode(file_part["inline_data"]["data"]) == b"%PDF-1.7"
    assert text_part == {"text": "read this"}
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["generationConfig"]["responseJsonSchema"] == {"type": "object"}


def test_gemini_body_is_unchanged_for_a_plain_prompt() -> None:
    body = gemini.build_body(_request())

    assert body["contents"][0]["parts"] == [{"text": "read this"}]
    assert body["generationConfig"] == {"maxOutputTokens": 100}


def test_anthropic_sends_a_pdf_as_a_document_and_states_the_schema() -> None:
    body = anthropic_provider.build_body(
        _request(
            attachments=(Attachment("application/pdf", b"%PDF"), Attachment("image/png", b"png")),
            json_schema={"type": "object"},
        )
    )

    document, image, text = body["messages"][0]["content"]
    assert document["type"] == "document"
    assert image["type"] == "image"
    assert image["source"]["media_type"] == "image/png"
    assert "JSON Schema" in text["text"]

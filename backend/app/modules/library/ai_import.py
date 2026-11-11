"""Reading a syllabus PDF or photo into import rows, with AI.

The spreadsheet import needs someone to type the syllabus into the template first. This
takes the document itself: Gemini reads it (scanned pages included) and answers with the
outline as JSON, which is flattened into exactly the rows the spreadsheet would hold.

**Nothing is written here.** The rows go back to the reviewer, who corrects them, checks
them with a dry run and only then imports them through ``service.import_rows`` — the same
validation and tree writer as a spreadsheet. An AI misreading costs an edit, never a
broken syllabus.

The call goes through the AI gateway as the ``syllabus_import`` feature, so the platform
kill switch, the institute's budget, the daily role limit and the usage log all apply.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Final

from fastapi import UploadFile

from app.core.db import Db
from app.core.errors import ValidationFailed
from app.modules.ai import gateway
from app.modules.ai.providers import Attachment
from app.modules.files.service import read_limited
from app.modules.files.validation import validate_upload
from app.modules.library import schemas, spreadsheet
from app.modules.library.service import authorize
from app.modules.rbac.service import Authorized

logger = logging.getLogger(__name__)

FEATURE_KEY: Final = "syllabus_import"
#: A long syllabus takes a while to write out. Below Cloud Run's 300 s request limit even
#: if the gateway has to try the fallback model as well.
TIMEOUT_SECONDS: Final = 120.0

_NAME: Final = {"type": "string"}
_TOPICS: Final = {"type": "array", "items": _NAME}
OUTLINE_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        # Listed first, so the model commits to every paper before writing the outline —
        # and the server can tell the reviewer which ones the outline then left out.
        "papers": {"type": "array", "items": _NAME},
        "levels": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": _NAME,
                    "subjects": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": _NAME,
                                "units": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "name": _NAME,
                                            "topics": _TOPICS,
                                            "chapters": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "name": _NAME,
                                                        "topics": _TOPICS,
                                                    },
                                                    "required": ["name", "topics"],
                                                },
                                            },
                                        },
                                        "required": ["name"],
                                    },
                                },
                            },
                            "required": ["name", "units"],
                        },
                    },
                },
                "required": ["name", "subjects"],
            },
        },
    },
    "required": ["papers", "levels"],
}

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")

#: How the document maps onto the tree. Kept in code, next to the schema it describes,
#: rather than in the admin-editable system prompt: the two must change together.
MAPPING_GUIDE: Final = """\
How to fill the outline:
- papers: first, the name of every paper or subject in the whole document, as named in
  "subjects" below. Then fill "levels" with every one of them.
- levels: the stages or classes the document covers, e.g. "Prelims (Stage I)" and
  "Mains (Stage II)", or "Class 10", or "Semester 8". Never the exam or board's name alone.
- subjects: each paper or subject inside a level, e.g. "Paper II - Geology", "Physics".
- units: each section, part or numbered heading inside a subject, e.g. "1. Physical Geology",
  "Section A - Mineralogy", "Unit 3: Thermodynamics".
- chapters: only when a unit is itself split into named chapters; otherwise leave empty.
- topics: the individual items studied inside a unit or chapter. A section's text usually
  lists them separated by semicolons, commas or full stops; make each one its own topic.
  A section heading is a unit, never a topic.
- Name every topic in at most 12 words, in your own words where the document's sentence is
  long. Do not copy whole paragraphs.
- Cover every section of the document, in the document's order. Do not skip any paper.
- Write every name in English, in Latin letters only. When the document (or one paper of
  it) is in Hindi, Marathi or another Indian language, translate each name into English,
  e.g. "हिंदी औपचारिक लेखन" becomes "Formal Writing in Hindi". The platform builds a code
  from each name and cannot from Devanagari. Translate such a paper; never leave it out.
"""


def instructions(level_hint: str | None) -> str:
    """What the reviewer asked for, in their words. It goes inside the gateway's user
    delimiters, so nothing typed here can override the feature's own instructions."""
    lines = ["Extract the syllabus outline from the attached document."]
    if level_hint:
        lines.append(f"The level is called: {level_hint}")
    return "\n".join(lines)


def parse_outline(text: str) -> dict[str, Any]:
    try:
        outline = json.loads(_FENCE.sub("", text.strip()))
    except json.JSONDecodeError as exc:
        # Almost always an answer cut off at the token limit: the document is too long.
        raise ValidationFailed(
            "The AI could not read the whole syllabus in one go. Please split the PDF into "
            "smaller parts (for example one paper or a few pages each) and import each part."
        ) from exc
    if not isinstance(outline, dict) or not isinstance(outline.get("levels"), list):
        raise ValidationFailed("The AI did not return a syllabus outline. Please try again.")
    return outline


def _names(items: Any) -> list[dict[str, Any]]:
    """Entries with a usable name; anything else the model returned is skipped."""
    if not isinstance(items, list):
        return []
    return [i for i in items if isinstance(i, dict) and str(i.get("name") or "").strip()]


def _topics(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [str(t).strip() for t in items if isinstance(t, str | int | float) and str(t).strip()]


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def missing_papers(outline: dict[str, Any]) -> list[str]:
    """Papers the model listed but then left out of the outline — shown to the reviewer,
    so an incomplete reading is visible instead of silently importing part of a syllabus."""
    listed = _topics(outline.get("papers"))
    present = {
        _key(str(subject["name"]))
        for level in _names(outline.get("levels"))
        for subject in _names(level.get("subjects"))
    }
    missing: list[str] = []
    for paper in listed:
        key = _key(paper)
        found = any(key and (key in p or p in key) for p in present if p)
        if key and not found and paper not in missing:
            missing.append(paper)
    return missing


def flatten(
    outline: dict[str, Any],
    *,
    track: str,
    level_hint: str | None,
    medium: str,
    difficulty: str,
    exam_tags: str,
) -> list[dict[str, str]]:
    """One row per topic, exactly as a person would fill the template.

    A unit or chapter with no topics still gets a row, so it is not lost. Repeated paths
    are kept once. With a single level and a ``level_hint``, the hint names the level —
    the reviewer knows better than the document what the level is called on the platform.
    """
    levels = _names(outline.get("levels"))
    rename = bool(level_hint) and len(levels) == 1

    rows: list[dict[str, str]] = []
    seen: set[tuple[str, ...]] = set()

    def add(*path: str) -> None:
        level, subject, unit, chapter, topic = (" ".join(p.split()) for p in path)
        key = (level.lower(), subject.lower(), unit.lower(), chapter.lower(), topic.lower())
        if key in seen:
            return
        seen.add(key)
        rows.append(
            {
                "track": track,
                "level": level,
                "subject": subject,
                "unit": unit,
                "chapter": chapter,
                "topic": topic,
                "medium": medium,
                "difficulty": difficulty,
                "exam_tags": exam_tags,
            }
        )

    for level in levels:
        level_name = str(level_hint if rename else level["name"])
        for subject in _names(level.get("subjects")):
            subject_name = str(subject["name"])
            units = _names(subject.get("units"))
            if not units:
                add(level_name, subject_name, "", "", "")
            for unit in units:
                unit_name = str(unit["name"])
                topics = _topics(unit.get("topics"))
                chapters = _names(unit.get("chapters"))
                for topic in topics:
                    add(level_name, subject_name, unit_name, "", topic)
                for chapter in chapters:
                    chapter_topics = _topics(chapter.get("topics"))
                    for topic in chapter_topics:
                        add(level_name, subject_name, unit_name, str(chapter["name"]), topic)
                    if not chapter_topics:
                        add(level_name, subject_name, unit_name, str(chapter["name"]), "")
                if not topics and not chapters:
                    add(level_name, subject_name, unit_name, "", "")
    return rows


async def extract(
    db: Db,
    *,
    guard: Authorized,
    upload: UploadFile,
    track: str,
    institute_id: uuid.UUID | None,
    level_hint: str | None,
    medium: str,
    difficulty: str,
    exam_tags: str,
) -> schemas.AiExtractResult:
    await authorize(guard, institute_id)
    clean = validate_upload(
        await read_limited(upload), declared_type=upload.content_type, filename=upload.filename
    )
    result = await gateway.complete(
        db,
        context=guard.context,
        institute_id=institute_id,
        feature_key=FEATURE_KEY,
        prompt=instructions(level_hint),
        extra_context=MAPPING_GUIDE,
        attachments=(Attachment(clean.content_type, clean.data),),
        json_schema=OUTLINE_SCHEMA,
        timeout_seconds=TIMEOUT_SECONDS,
    )
    if result.safety_blocked:
        raise ValidationFailed("The AI declined to read this document. Please check the file.")

    outline = parse_outline(result.text)
    cells = flatten(
        outline,
        track=track,
        level_hint=level_hint,
        medium=medium,
        difficulty=difficulty,
        exam_tags=exam_tags,
    )
    if not cells:
        raise ValidationFailed(
            "No syllabus was found in that file. Please upload the syllabus pages themselves."
        )
    if len(cells) > spreadsheet.MAX_ROWS:
        raise ValidationFailed(
            f"That syllabus has more than {spreadsheet.MAX_ROWS} topics. Please split the PDF."
        )
    checked = spreadsheet.rows_from_cells(cells)
    logger.info(
        "syllabus read by ai",
        extra={"rows": len(cells), "model_id": result.model_id, "status": result.status},
    )
    return schemas.AiExtractResult(
        file_name=clean.original_name,
        model_id=result.model_id,
        status=result.status,
        cost_paise=result.cost_paise,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        missing_papers=missing_papers(outline),
        rows=[
            schemas.ImportRowCells(**row, problems=parsed.problems)
            for row, parsed in zip(cells, checked, strict=True)
        ],
    )

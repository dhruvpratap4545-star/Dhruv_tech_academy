"""Content Library pure rules: codes, paths, video links, import rows, seed files."""

from __future__ import annotations

import pytest

from app.core.errors import ValidationFailed
from app.modules.library import seed, spreadsheet
from app.modules.library.rules import (
    check_https_link,
    check_kind,
    child_path,
    normalise_code,
    parse_video_url,
    slugify,
)


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("Light – Reflection and Refraction", "light-reflection-and-refraction"),
        ("What's in a Name?", "what-s-in-a-name"),
        ("  Class 10  ", "class-10"),
        ("Électricité", "electricite"),
        ("विज्ञान", ""),
    ],
)
def test_slugify(name: str, code: str) -> None:
    assert slugify(name) == code


def test_a_code_needs_latin_letters_or_digits() -> None:
    with pytest.raises(ValidationFailed):
        normalise_code("विज्ञान")
    assert normalise_code("Ch 1") == "ch-1"


def test_code_paths_chain_from_the_track() -> None:
    assert child_path(None, "cbse") == "cbse"
    assert child_path("cbse/class-10", "science") == "cbse/class-10/science"


def test_kinds_must_deepen_and_tracks_are_roots() -> None:
    check_kind(None, "track")
    check_kind("track", "level")
    check_kind("subject", "topic")  # units and chapters may be skipped
    for parent, kind in [
        (None, "level"),
        ("chapter", "unit"),
        ("level", "track"),
        ("topic", "topic"),
    ]:
        with pytest.raises(ValidationFailed):
            check_kind(parent, kind)


@pytest.mark.parametrize(
    ("url", "provider", "video_id"),
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=40s", "youtube", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ?si=tracking", "youtube", "dQw4w9WgXcQ"),
        ("https://m.youtube.com/shorts/dQw4w9WgXcQ", "youtube", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", "youtube", "dQw4w9WgXcQ"),
        ("https://vimeo.com/76979871", "vimeo", "76979871"),
        ("https://player.vimeo.com/video/76979871", "vimeo", "76979871"),
    ],
)
def test_video_links_are_normalised_to_an_id(url: str, provider: str, video_id: str) -> None:
    video = parse_video_url(url)
    assert (video.provider, video.video_id) == (provider, video_id)
    assert video.url.startswith("https://")


@pytest.mark.parametrize(
    "url",
    [
        "http://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=short",
        "https://www.youtube.com/channel/abc",
        "https://example.com/video.mp4",
        "javascript:alert(1)",
        "https://vimeo.com/channels/staffpicks",
    ],
)
def test_other_links_are_refused_as_videos(url: str) -> None:
    with pytest.raises(ValidationFailed):
        parse_video_url(url)


def test_reading_links_must_be_plain_https() -> None:
    assert (
        check_https_link(" https://ncert.nic.in/textbook.php ")
        == "https://ncert.nic.in/textbook.php"
    )
    for bad in (
        "http://ncert.nic.in",
        "ftp://x.org/a",
        "https://user:pw@x.org",
        "https://localhost",
    ):
        with pytest.raises(ValidationFailed):
            check_https_link(bad)


def test_an_import_row_is_validated_with_every_problem_reported() -> None:
    good = spreadsheet.validate_row(
        2,
        {
            "track": "CBSE",
            "level": "Class 10",
            "subject": "Science",
            "chapter": "Electricity",
            "topic": "Ohm's Law",
            "medium": "Both",
            "difficulty": "Medium",
            "exam_tags": "CBSE, JEE",
        },
    )
    assert good.problems == []
    assert good.track == "cbse"
    assert [k for k, _ in good.path] == ["level", "subject", "chapter", "topic"]
    assert good.mediums == ["hi", "en"] and good.difficulty == "medium"
    assert good.exam_tags == ["cbse", "jee"]

    bad = spreadsheet.validate_row(
        3,
        {
            "track": "ICSE",
            "subject": "Science",
            "topic": "Ohm",
            "medium": "French",
            "difficulty": "x",
        },
    )
    text = " ".join(bad.problems)
    for expected in (
        "Track must be",
        "Level is required",
        "topic needs",
        "Medium must",
        "Difficulty",
    ):
        assert expected in text


def test_the_template_round_trips_through_the_reader() -> None:
    rows = spreadsheet.read_rows(spreadsheet.template())
    assert [r.number for r in rows] == [2, 3]
    assert all(not r.problems for r in rows)


def test_a_non_workbook_is_refused() -> None:
    with pytest.raises(ValidationFailed, match="not an Excel"):
        spreadsheet.read_rows(b"not a spreadsheet")


@pytest.mark.parametrize("track", seed.SEEDED_TRACKS)
def test_every_seed_file_records_its_source_and_has_valid_kinds(track: str) -> None:
    data = seed.load_file(track)
    assert data["track"] == track
    assert data["source"] and data["as_of"] and "verification" in data["note"]

    def walk(kind: str, spec: dict) -> int:
        count = 0
        for child in seed.children_of(spec):
            check_kind(kind, child["kind"])
            assert slugify(child.get("code") or child["name"]), child["name"]
            count += 1 + walk(child["kind"], child)
        return count

    assert walk("track", data) > 50


def test_cbse_covers_classes_1_to_12_with_topics_from_class_9() -> None:
    data = seed.load_file("cbse")
    levels = {lvl["code"]: lvl for lvl in data["levels"]}
    assert list(levels) == [f"class-{n}" for n in range(1, 13)]
    for n in (9, 10, 11, 12):
        science_like = [
            s for s in levels[f"class-{n}"]["subjects"] if s["name"] != "Social Science"
        ]
        for subject in science_like:
            assert all(c.get("topics") for c in subject["chapters"]), (n, subject["name"])

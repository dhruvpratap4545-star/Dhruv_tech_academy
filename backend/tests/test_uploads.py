"""Upload validation and local storage (Phase 3 shared groundwork). No database needed."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from app.core.errors import ValidationFailed
from app.core.storage import LocalStorage
from app.modules.files import validation
from app.modules.files.validation import JPEG, PDF, PNG, safe_name, sniff, validate_upload

PDF_BYTES = b"%PDF-1.7\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


def _jpeg(size=(64, 48), *, gps: bool = False) -> bytes:
    image = Image.new("RGB", size, (200, 30, 30))
    out = io.BytesIO()
    if gps:
        exif = Image.Exif()
        exif[0x010F] = "PhoneMaker"  # Make
        exif[0x8825] = {1: "N", 2: (18.0, 31.0, 12.0)}  # GPS IFD: latitude
        image.save(out, format="JPEG", exif=exif)
    else:
        image.save(out, format="JPEG")
    return out.getvalue()


def _png(size=(32, 32)) -> bytes:
    out = io.BytesIO()
    Image.new("RGBA", size, (0, 0, 255, 128)).save(out, format="PNG")
    return out.getvalue()


def test_sniff_reads_the_real_type_from_the_bytes() -> None:
    assert sniff(PDF_BYTES) == PDF
    assert sniff(_jpeg()) == JPEG
    assert sniff(_png()) == PNG
    assert sniff(b"MZ\x90\x00 an executable") is None


def test_a_renamed_executable_is_refused() -> None:
    with pytest.raises(ValidationFailed, match="Only PDF, JPG and PNG"):
        validate_upload(b"MZ\x90\x00binary", declared_type="image/jpeg", filename="hw.jpg")


def test_contents_must_match_the_declared_type() -> None:
    with pytest.raises(ValidationFailed, match="do not match"):
        validate_upload(PDF_BYTES, declared_type="image/png", filename="x.png")


def test_a_generic_declared_type_is_decided_by_the_bytes() -> None:
    clean = validate_upload(PDF_BYTES, declared_type="application/octet-stream", filename="a")
    assert clean.content_type == PDF
    assert clean.data == PDF_BYTES  # PDFs are stored as they are


def test_jpg_alias_is_accepted() -> None:
    assert (
        validate_upload(_jpeg(), declared_type="image/jpg", filename="a.jpg").content_type == JPEG
    )


def test_empty_and_oversized_files_are_refused(monkeypatch) -> None:
    with pytest.raises(ValidationFailed, match="empty"):
        validate_upload(b"", declared_type=None, filename=None)
    monkeypatch.setattr(validation, "max_bytes", lambda: 10)
    with pytest.raises(ValidationFailed, match="at most"):
        validate_upload(PDF_BYTES, declared_type=PDF, filename="big.pdf")


def test_exif_and_gps_are_stripped_from_photos() -> None:
    original = _jpeg(gps=True)
    assert Image.open(io.BytesIO(original)).getexif().get(0x010F) == "PhoneMaker"

    clean = validate_upload(original, declared_type=JPEG, filename="notebook.jpg")

    exif = Image.open(io.BytesIO(clean.data)).getexif()
    assert 0x010F not in exif
    assert 0x8825 not in exif


def test_large_photos_are_scaled_to_the_maximum_edge() -> None:
    clean = validate_upload(_jpeg((3000, 1500)), declared_type=JPEG, filename="big.jpg")
    assert Image.open(io.BytesIO(clean.data)).size == (2000, 1000)


def test_png_transparency_survives_reencoding() -> None:
    clean = validate_upload(_png(), declared_type=PNG, filename="d.png")
    assert Image.open(io.BytesIO(clean.data)).mode == "RGBA"


def test_a_corrupt_image_is_refused_politely() -> None:
    broken = b"\xff\xd8\xff\xe0" + b"\x00" * 50
    with pytest.raises(ValidationFailed, match="could not be read"):
        validate_upload(broken, declared_type=JPEG, filename="x.jpg")


def test_the_hash_is_of_the_stored_bytes() -> None:
    import hashlib

    clean = validate_upload(_jpeg(), declared_type=JPEG, filename="a.jpg")
    assert clean.sha256 == hashlib.sha256(clean.data).hexdigest()


@pytest.mark.parametrize(
    ("given", "content_type", "expected"),
    [
        ("../../etc/passwd", PDF, "passwd.pdf"),
        ("C:\\Users\\a\\Homework 1.pdf", PDF, "Homework 1.pdf"),
        ('evil"; filename=x.exe', JPEG, "evil_ filename_x.jpg"),
        (None, PNG, "file.png"),
        ("photo.jpeg.exe", JPEG, "photo.jpeg.jpg"),
    ],
)
def test_display_names_cannot_carry_paths_or_header_injection(given, content_type, expected):
    assert safe_name(given, content_type) == expected


async def test_local_storage_round_trips_and_refuses_escaping_keys(tmp_path) -> None:
    storage = LocalStorage(tmp_path)
    await storage.put("inst/homework_attachment/abc", b"hello", "application/pdf")
    assert await storage.open("inst/homework_attachment/abc") == b"hello"
    assert await storage.signed_url("inst/x", ttl_seconds=60, filename="a.pdf") is None
    with pytest.raises(ValueError, match="escapes"):
        await storage.put("../outside", b"x", "application/pdf")

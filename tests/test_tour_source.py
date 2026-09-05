from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi import HTTPException

from vera_tour_source import canonical_tour_url, extract_tour_file_id
from vera_web_v2_tour_source import _validate_tour_workbook


FILE_ID = "15nDSicFhEHstxQjGrETuSK8Z7q6cSQyS"


@pytest.mark.parametrize(
    "value",
    [
        FILE_ID,
        f"https://drive.google.com/file/d/{FILE_ID}/view?usp=sharing",
        f"https://drive.google.com/open?id={FILE_ID}",
        f"https://docs.google.com/spreadsheets/d/{FILE_ID}/edit",
    ],
)
def test_extract_tour_file_id(value):
    assert extract_tour_file_id(value) == FILE_ID


def test_rejects_non_google_link():
    with pytest.raises(ValueError, match="Google Drive"):
        extract_tour_file_id(f"https://example.com/{FILE_ID}")


def test_canonical_tour_url():
    assert canonical_tour_url(FILE_ID) == f"https://drive.google.com/file/d/{FILE_ID}/view"


def test_validate_tour_workbook_requires_macro_and_expected_sheets():
    stream = BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        archive.writestr("xl/vbaProject.bin", b"vba")
        archive.writestr(
            "xl/workbook.xml",
            '<workbook><sheets><sheet name="Input"/><sheet name="Room"/><sheet name="Nghi"/></sheets></workbook>',
        )
    _validate_tour_workbook(stream.getvalue())


def test_validate_tour_workbook_rejects_wrong_file():
    with pytest.raises(HTTPException):
        _validate_tour_workbook(b"not-a-workbook")

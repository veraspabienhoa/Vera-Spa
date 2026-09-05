from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_new_employee_form_only_contains_the_seven_requested_fields():
    source = (ROOT / "web-v2/src/pages/EmployeePage.jsx").read_text(encoding="utf-8")
    form = source.split("{addOpen &&", 1)[1].split("{profileUser &&", 1)[0]

    assert form.count("<label>") == 7
    for label in (
        "Tên nhân viên",
        "Mật khẩu ban đầu (tối thiểu 8 ký tự)",
        "Phân quyền",
        "Ngày bắt đầu làm",
        "Họ và tên đầy đủ",
        "Ngày sinh",
        "Giới tính",
    ):
        assert label in form

    assert "required-star" in form
    assert "createPasswordVisible" in form
    assert "<EmployeeMediaDraftPanel" not in form
    for omitted in ("Dân tộc", "Số Căn cước", "Điện thoại", "Tên ngân hàng"):
        assert omitted not in form


def test_new_employee_defaults_and_server_requirements_match():
    page = (ROOT / "web-v2/src/pages/EmployeePage.jsx").read_text(encoding="utf-8")
    api = (ROOT / "vera_web_v2_staff.py").read_text(encoding="utf-8")

    assert "password: 'Vera123456'" in page
    assert "role: 'nhanvien'" in page
    assert 'password: str = Field(default="Vera123456", min_length=8' in api
    assert 'field_name="Ngày bắt đầu làm", allow_blank=False' in api
    assert 'field_name="Ngày sinh", allow_blank=False' in api
    assert "Giới tính không được để trống." in api


def test_shared_date_control_displays_vietnamese_date_format():
    source = (ROOT / "web-v2/src/components/VeraDateInput.jsx").read_text(encoding="utf-8")

    assert 'placeholder="dd/mm/yyyy"' in source
    assert "parseVeraDate" in source
    assert "formatVeraDate" in source
    assert "showPicker" in source

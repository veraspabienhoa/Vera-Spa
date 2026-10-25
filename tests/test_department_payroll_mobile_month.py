from pathlib import Path


def test_department_payroll_month_input_fits_mobile_width():
    css = Path("web-v2/src/styles.css").read_text(encoding="utf-8")

    assert ".department-payroll-toolbar>label{min-width:0;width:100%;max-width:100%}" in css
    assert ".department-payroll-toolbar>label input[type=month]{display:block;width:100%;min-width:0;max-width:100%;box-sizing:border-box;font-size:16px}" in css

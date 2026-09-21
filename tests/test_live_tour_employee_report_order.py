from pathlib import Path


def test_employee_statistics_are_below_both_employee_charts():
    source = Path("web-v2/src/components/LiveTourEmployeeRevenueBreakdown.jsx").read_text(encoding="utf-8")

    service_chart = 'label="Biểu đồ dịch vụ theo nhân viên"'
    heading = '<h3>THỐNG KÊ THEO NHÂN VIÊN</h3>'
    tip_chart = 'label="Biểu đồ tiền TIP theo nhân viên"'

    assert service_chart in source
    assert heading in source
    assert tip_chart in source
    assert source.index(service_chart) < source.index(tip_chart) < source.index(heading)

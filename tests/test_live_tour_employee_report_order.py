from pathlib import Path


def test_employee_service_chart_is_above_employee_statistics_heading():
    source = Path("web-v2/src/components/LiveTourEmployeeRevenueBreakdown.jsx").read_text(encoding="utf-8")

    service_chart = 'label="Biểu đồ tiền dịch vụ theo nhân viên"'
    heading = '<h3>THỐNG KÊ THEO NHÂN VIÊN</h3>'
    tip_chart = 'label="Biểu đồ tiền TIP theo nhân viên"'

    assert service_chart in source
    assert heading in source
    assert tip_chart in source
    assert source.index(service_chart) < source.index(heading) < source.index(tip_chart)

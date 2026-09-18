from pathlib import Path


def test_employee_charts_have_independent_sorting_and_service_only_capture():
    source = Path("web-v2/src/components/LiveTourEmployeeRevenueBreakdown.jsx").read_text(encoding="utf-8")

    assert 'label="Biểu đồ dịch vụ theo nhân viên"' in source
    assert 'valueKey="rows"' in source
    assert 'label="Biểu đồ tiền TIP theo nhân viên"' in source
    assert "const [serviceSort, setServiceSort] = useState('value_desc')" in source
    assert "const [tipSort, setTipSort] = useState('value_desc')" in source
    for option in ("value_desc", "value_asc", "name_asc", "name_desc"):
        assert f'value="{option}"' in source

    assert "copyServiceChart" in source
    assert "serviceChartRef.current" in source
    assert "elementToPngBlob(serviceChartRef.current)" in source
    assert source.count("onCapture={copyServiceChart}") == 1
    assert "hideValuesInSnapshot" in source
    assert "data-snapshot-ignore={hideValuesInSnapshot ? true : undefined}" in source
    assert "Chụp toàn bộ section & copy" not in source

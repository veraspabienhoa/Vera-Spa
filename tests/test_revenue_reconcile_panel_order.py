from pathlib import Path


def test_revenue_reconcile_shows_ledger_input_on_left():
    source = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")

    grid = source.split('<div className="reconcile-grid">', 1)[1].split('</div>\n\n        <div className="revenue-meta">', 1)[0]
    ledger = grid.index("Quản lý Thu Chi · Input")
    purchase = grid.index("BaoCaoMuaHang.xlsb · Input")

    assert ledger < purchase

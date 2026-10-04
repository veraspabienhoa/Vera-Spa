from datetime import date, datetime
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
import vera_revenue_report as report


@pytest.fixture
def frozen(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 4, tzinfo=tz)
    monkeypatch.setattr(report.source, 'datetime', Clock)


def test_full_first_half_allowed_only_as_read_filter(frozen):
    for mode in ['manual', 'auto', 'manual_tip_auto']:
        assert report.resolve_period(None, date(2026, 10, 1), date(2026, 10, 15), mode=mode, calendar_filter=True) == (date(2026, 10, 1), date(2026, 10, 15))
        with pytest.raises(HTTPException):
            report.resolve_period(None, date(2026, 10, 1), date(2026, 10, 15), mode=mode)
    for start, end in [(date(2026,10,1),date(2026,10,16)),(date(2026,10,2),date(2026,10,15)),(date(2026,11,1),date(2026,11,15))]:
        with pytest.raises(HTTPException):
            report.resolve_period(None,start,end,mode='auto',calendar_filter=True)


@pytest.mark.parametrize('mode',['manual','auto'])
def test_snapshot_keeps_calendar_dates_and_counts_only_actual_days(frozen,monkeypatch,mode):
    calls=[]
    monkeypatch.setattr(report.source,'mode',lambda _: {'source':mode,'revision':1})
    monkeypatch.setattr(report.source,'daily',lambda _,start,end,**kw: calls.append(('daily',end)) or [])
    monkeypatch.setattr(report.source,'totals',lambda _:dict(total_income=100,total_expense=10,net_income=90))
    monkeypatch.setattr(report.source,'tip_total',lambda _,start,end,**kw: calls.append(('tip',end)) or 20)
    class Conn:
        def execute(self, query, params):
            calls.append(('manual',params['end']))
            return SimpleNamespace(mappings=lambda:SimpleNamespace(one=lambda:dict(income=100,expense=10)))
    result=report.snapshot(Conn(),date(2026,10,1),date(2026,10,15),calendar_filter=True)
    assert result['period_tip_end']=='2026-10-15'
    assert result['balance']==70
    assert all(end==date(2026,10,4) for _,end in calls)

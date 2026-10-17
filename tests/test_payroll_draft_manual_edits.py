import vera_web_v2_payroll as payroll


def test_clean_snapshot_preserves_only_allowed_edit_markers(monkeypatch):
    employee=dict(username='A',full_name='Employee A',email='',bank_account='',bank_name='')
    monkeypatch.setattr(payroll,'_employee_catalog',lambda *_:{'a':employee})
    row={'Tên Hệ thống':'A','Tiền Lương':1000000,'Tích lũy':0,
         'Tiền ứng lương':123000,'__manual_overrides':{'Tích lũy':999,'Tiền ứng lương':999,'Tiền Lương':999}}
    result=payroll._clean_draft_rows(None,[row],lambda x:str(x or '').lower())[0]
    assert result['__manual_overrides']=={'Tích lũy':0,'Tiền ứng lương':123000}
    assert result['Số tiền thực nhận']==877000


def test_open_saved_draft_does_not_refresh_saved_financial_values(monkeypatch):
    from datetime import date
    row={'Tên Hệ thống':'A','Tiền Lương':1000000,'Tích lũy':0,'Tiền ứng lương':123000}
    class Connection:
        def execute(self,*args,**kwargs): return self
        def mappings(self): return self
        def first(self): return {'value_json':{'rows':[row]},'updated_by':'admin','updated_at':None}
    monkeypatch.setattr(payroll,'_employee_catalog',lambda *_:{'a':{'username':'A'}})
    import vera_attendance_participation as participation
    monkeypatch.setattr(participation,'suspended',lambda *_:False)
    def clean(conn,rows,norm,**kwargs):
        assert not kwargs.get('refresh_financial',False)
        return rows
    monkeypatch.setattr(payroll,'_clean_draft_rows',clean)
    result=payroll._saved_draft(Connection(),date(2026,10,1),date(2026,10,15),lambda x:str(x or '').lower())
    assert result['rows']==[row]

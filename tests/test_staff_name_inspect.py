from vera_staff_name_inspect import inspect


def test_inspection_read_only_filters_names_and_does_not_expose_payload():
    queries = []
    class Result:
        def mappings(self): return self
        def all(self):
            return [
                {'username': 'New', 'payload': {'__deleted': True, 'employment_status': 'Đã nghỉ việc'}},
                {'username': 'Different', 'payload': {'__previous_usernames': ['New'], 'secret': 'never-output'}},
                {'username': 'Other', 'payload': {}},
            ]
    class Conn:
        def execute(self, query):
            queries.append(str(query))
            return Result()
    result = inspect(Conn(), 'new')
    assert queries[0] == 'SET TRANSACTION READ ONLY'
    assert [m['username'] for m in result['matches']] == ['New', 'Different']
    assert result['matches'][0]['deleted']
    assert not result['matches'][1]['current_name_match']
    assert not result['database_writes']
    assert 'secret' not in str(result) and 'never-output' not in str(result)

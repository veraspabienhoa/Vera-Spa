from sqlalchemy import create_engine, text

from vera_web_v2_training import _report_employees


def test_report_search_requires_actual_results_and_preserves_permitted_catalog():
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE vera_training_session (employee_username TEXT)'))
        conn.execute(text('CREATE TABLE vera_evaluation_assignment (id INTEGER, employee_username TEXT, status TEXT)'))
        conn.execute(text('CREATE TABLE vera_employee_evaluation (assignment_id INTEGER)'))
        conn.execute(text("INSERT INTO vera_training_session VALUES ('DAILY'), ('outside_permission')"))
        conn.execute(text("INSERT INTO vera_evaluation_assignment VALUES (1,'evaluated','submitted'), (2,'draft','draft'), (3,'empty','submitted'), (4,'assigned','pending')"))
        conn.execute(text('INSERT INTO vera_employee_evaluation VALUES (1), (2)'))
        # Even an old daily assessment remains eligible beyond the 300-row recent list.
        conn.execute(text('INSERT INTO vera_training_session VALUES (:name)'), [{'name': f'recent{i}'} for i in range(301)])
        people = [{'username': name} for name in ('daily', 'evaluated', 'draft', 'empty', 'assigned', 'no_data')]
        assert _report_employees(conn, people) == people[:2]
        assert _report_employees(conn, []) == []

from sqlalchemy import text
from vera_postgres_job_queue import ensure_schema_conn
from vera_technical_retention import run
from test_live_tour_resource_postgres import database


def test_only_completed_old_projection_jobs_are_deleted(database):
    with database.begin() as conn:
        ensure_schema_conn(conn)
        for name,status,age,queue,locked in [
            ('old','done',4,'live_tour_projection',False),
            ('recent','done',2,'live_tour_projection',False),
            ('processing','processing',4,'live_tour_projection',True),
            ('retry','retry',4,'live_tour_projection',False),
            ('failed','failed',4,'live_tour_projection',False),
            ('financial','done',4,'payment_queue',False),
        ]:
            conn.execute(text("""INSERT INTO vera_background_job(queue_name,job_key,status,completed_at,locked_at)
              VALUES(:queue,:name,:status,NOW()-make_interval(days=>:age),CASE WHEN :locked THEN NOW() ELSE NULL END)"""),locals())
    assert run(database)=={'dry_run':True,'eligible':1,'removed':0,'retention_hours':72}
    result=run(database,apply=True)
    assert result['removed']==1
    with database.connect() as conn:
        names=set(conn.execute(text('SELECT job_key FROM vera_background_job')).scalars())
        assert names=={'recent','processing','retry','failed','financial'}
        assert conn.execute(text('SELECT count(*) FROM vera_live_tour_meta')).scalar_one()==1


def test_cleanup_skips_locked_completed_job(database):
    with database.begin() as conn:
        ensure_schema_conn(conn)
        conn.execute(text("INSERT INTO vera_background_job(queue_name,job_key,status,completed_at) VALUES('live_tour_projection','locked-done','done',NOW()-INTERVAL '4 days')"))
    with database.begin() as writer:
        writer.execute(text("SELECT id FROM vera_background_job WHERE job_key='locked-done' FOR UPDATE"))
        assert run(database, apply=True)['removed'] == 0
    assert run(database, apply=True)['removed'] == 1

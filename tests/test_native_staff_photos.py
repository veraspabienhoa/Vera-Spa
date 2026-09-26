"""Native-size photo storage and opt-in Excel framing, including actual PostgreSQL."""
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from PIL import Image
from sqlalchemy import text

from test_capture_face_id_assignment import fixture  # noqa: F401
from test_face_id_photos import png
import vera_web_v2_staff_security as security
from vera_staff_photo_export import read_portraits, portrait_frame


def install_security(db, api):
    security.install_staff_security_routes(api.app, engine_instance=lambda: db,
        current_identity=lambda: SimpleNamespace(role='admin', employee_username='admin'),
        require_feature=lambda *_: None, norm=lambda value: str(value).casefold(), identity_type=object)


@pytest.mark.parametrize('size', [(400,300), (300,300), (80,120), (120,80)])
def test_portrait_keeps_original_bytes_and_small_cccd_is_still_rejected(fixture, size):
    db, api, _ = fixture
    install_security(db, api)
    original = png(*size)
    path = '/v2/staff/Ánh Thử/identity/'
    response = api.put(path+'portrait', content=original, headers={'Content-Type':'image/png'})
    assert response.status_code == 200, response.text
    assert api.get(path+'portrait').content == original
    assert api.put(path+'front', content=png(80,120), headers={'Content-Type':'image/png'}).status_code == 400
    assert api.put(path+'portrait', content=b'bad image', headers={'Content-Type':'image/png'}).status_code == 400
    assert api.put(path+'portrait', content=png(6001,10), headers={'Content-Type':'image/png'}).status_code == 400
    assert api.get(path+'portrait').content == original


def test_batch_export_only_reads_selected_portraits_and_never_changes_storage(fixture):
    db, api, _ = fixture
    install_security(db, api)
    original = png(120,80)
    assert api.put('/v2/staff/Ánh Thử/identity/portrait',content=original,headers={'Content-Type':'image/png'}).status_code == 200
    with db.begin() as conn:
        conn.execute(text("""INSERT INTO vera_employee_identity_document
            (employee_username,side,content_type,content,size_bytes,sha256) VALUES
            ('Other','portrait','image/png',:content,:size,'other'),
            ('Ánh Thử','front','image/png',:content,:size,'front')"""), {'content':png(color='red'),'size':len(png(color='red'))})
    with db.connect() as conn:
        photos = read_portraits(conn, ['Ánh Thử'])
        assert photos == {'Ánh Thử':original}
        assert read_portraits(conn, []) == {}
        assert read_portraits(conn, ['missing']) == {}
        with pytest.raises(HTTPException) as too_many:
            read_portraits(conn, [str(i) for i in range(201)])
        assert too_many.value.status_code == 400
    portrait_frame(photos['Ánh Thử'])
    assert api.get('/v2/staff/Ánh Thử/identity/portrait').content == original


def test_export_frame_preserves_landscape_edges_and_adds_white_space():
    source = Image.new('RGB',(120,80),'blue')
    source.paste('red',(0,0,12,80));source.paste('green',(108,0,120,80))
    stream=BytesIO();source.save(stream,format='PNG')
    frame = Image.open(BytesIO(portrait_frame(stream.getvalue())))
    assert frame.size == (300,400)
    assert frame.getpixel((150,0)) == (255,255,255)
    assert frame.getpixel((0,200)) == (255,0,0)
    assert frame.getpixel((299,200)) == (0,128,0)
    assert frame.getpixel((150,200)) == (0,0,255)

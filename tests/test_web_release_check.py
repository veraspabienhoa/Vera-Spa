import json

import pytest

import vera_web_release_check as release


SHA = 'a' * 40
INFO = {'revision': SHA, 'entry_script': '/assets/index-new.js'}
HTML = '<script type="module" crossorigin src="/assets/index-new.js"></script>'


def test_release_requires_matching_revision_and_actual_html_entry():
    assert release.validate_release(SHA, INFO, HTML) == INFO['entry_script']
    with pytest.raises(ValueError, match='revision'):
        release.validate_release(SHA, {**INFO, 'revision': 'b' * 40}, HTML)
    with pytest.raises(ValueError, match='different frontend'):
        release.validate_release(SHA, INFO, HTML.replace('index-new', 'index-old'))
    with pytest.raises(ValueError, match='different frontend'):
        release.validate_release(SHA, INFO, '<!-- ' + HTML + ' -->')


def test_bad_or_missing_metadata_cannot_confirm_a_deployment():
    for info in [None, [], {}, {**INFO, 'entry_script': 'https://other.test/assets/index-new.js'}]:
        with pytest.raises(ValueError):
            release.validate_release(SHA, info, HTML)
    with pytest.raises(ValueError, match='full Git'):
        release.validate_release('main', INFO, HTML)


def test_a_fresh_query_does_not_hide_a_stale_canonical_page(monkeypatch):
    calls = []
    def read(url):
        calls.append(url)
        if '/build-info.json?' in url:
            return json.dumps(INFO)
        return HTML.replace('index-new', 'index-old') if url.endswith('/') else HTML
    monkeypatch.setattr(release, 'read_public', read)
    with pytest.raises(ValueError, match='different frontend'):
        release.check_public_release('https://app.example.test', SHA)
    assert 'https://app.example.test/' in calls


def test_public_check_reads_both_canonical_and_recovery_documents(monkeypatch):
    calls = []
    def read(url):
        calls.append(url)
        return json.dumps(INFO) if '/build-info.json?' in url else HTML
    monkeypatch.setattr(release, 'read_public', read)
    assert release.check_public_release('https://app.example.test', SHA) == INFO['entry_script']
    assert calls == [f'https://app.example.test/build-info.json?revision={SHA}',
                     'https://app.example.test/', f'https://app.example.test/?vera_release={SHA}']

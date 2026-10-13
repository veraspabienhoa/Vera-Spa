from test_live_tour_date_permission_catalog import permission_client, grant, identity, FEATURES, _feature_allowed


def test_scoped_save_preserves_other_overrides_and_inheritance():
    client, store = permission_client({'roles':[grant('training_view',False,'letan')], 'accounts':[grant('profile_edit',False)]})
    allowed=[key for key in FEATURES if _feature_allowed(None,identity(),key,store['payload'])]
    response=client.put('/v2/permissions/account/operator',json={'allowed_features':[*allowed,'training_view'], 'edited_features':['training_view'], 'expected_revision':12,'preserve_unchanged':True,'date_filter_policy_version':1})
    assert response.status_code==200,response.text
    assert response.json()['scoped_permission_policy_version']==1
    assert store['payload']['accounts']==[grant('profile_edit',False),grant('training_view',True)]
    assert store['payload']['roles']==[grant('training_view',False,'letan')]
    assert client.get('/v2/permissions').json()['scoped_permission_policy_version']==1


def test_scoped_grant_adds_required_view_without_freezing_other_pages():
    client, store=permission_client()
    response=client.put('/v2/permissions/account/operator',json={'allowed_features':['training_session_create'], 'edited_features':['training_session_create'],'expected_revision':12,'preserve_unchanged':True})
    assert response.status_code==200,response.text
    rows={row['feature']:row['allowed'] for row in store['payload']['accounts']}
    assert rows=={'training_view':True,'training_session_create':True}


def test_scoped_save_rejects_missing_revision_and_stale_revision():
    client,store=permission_client()
    for revision,status in [(None,428),(11,409)]:
        response=client.put('/v2/permissions/account/operator',json={'allowed_features':['training_view'],'edited_features':['training_view'],'expected_revision':revision,'preserve_unchanged':True})
        assert response.status_code==status,response.text
    assert store['writes']==0


def test_performance_tab_grant_can_be_saved_and_revoked_without_other_changes():
    client, store = permission_client({'roles': [], 'accounts': [grant('profile_edit', False)]})
    response = client.put('/v2/permissions/account/operator', json={
        'allowed_features': ['live_tour_performance_view'], 'edited_features': ['live_tour_performance_view'],
        'expected_revision': 12, 'preserve_unchanged': True})
    assert response.status_code == 200, response.text
    rows = {row['feature']: row['allowed'] for row in store['payload']['accounts']}
    assert rows == {'profile_edit': False, 'live_tour_view': True, 'live_tour_reports_view': True, 'live_tour_performance_view': True}
    assert _feature_allowed(None, identity(), 'live_tour_performance_view', store['payload'])
    response = client.put('/v2/permissions/account/operator', json={
        'allowed_features': ['live_tour_view', 'live_tour_reports_view'], 'edited_features': ['live_tour_performance_view'],
        'expected_revision': response.json()['revision'], 'preserve_unchanged': True})
    assert response.status_code == 200, response.text
    assert not _feature_allowed(None, identity(), 'live_tour_performance_view', store['payload'])
    assert _feature_allowed(None, identity(), 'live_tour_reports_view', store['payload'])

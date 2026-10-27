import pytest
from app.security import create_access_token, hash_password
from app.models import User
from app import sms_auth
from tests.test_sms_auth import sms_store


async def setup(db):
    user=User(username='13900000001',email='account@example.com',password_hash=hash_password('old-test-password'))
    other=User(username='13900000002',email='other@example.com',password_hash=hash_password('other-password'))
    db.add_all([user,other]);await db.commit()
    return user,{'Authorization':'Bearer '+create_access_token(user.id)}


@pytest.mark.asyncio
async def test_profile_roundtrip_and_reject_blank(client,db_session):
    user,headers=await setup(db_session)
    assert (await client.get('/api/v1/account')).status_code==401
    data={'display_name':' Creator ','avatar_url':None}
    assert (await client.patch('/api/v1/account/profile',json=data,headers=headers)).status_code==200
    saved=(await client.get('/api/v1/account',headers=headers)).json()
    assert saved['display_name']=='Creator' and saved['phone']==user.username and saved['email_verified'] is False
    assert 'password_hash' not in saved
    assert (await client.patch('/api/v1/account/profile',json={'display_name':' '},headers=headers)).status_code==422


@pytest.mark.asyncio
async def test_password_change_revokes_access_and_refresh(client,db_session):
    user,headers=await setup(db_session)
    login=await client.post('/api/v1/auth/login',json={'username_or_email':user.username,'password':'old-test-password'})
    payload={'current_password':'incorrect-password','password':'new-test-password'}
    assert (await client.post('/api/v1/account/password',json=payload,headers=headers)).status_code==400
    payload['current_password']='old-test-password'
    assert (await client.post('/api/v1/account/password',json=payload,headers=headers)).status_code==200
    assert (await client.get('/api/v1/account',headers=headers)).status_code==401
    assert (await client.post('/api/v1/auth/refresh',json={'refresh_token':login.json()['refresh_token']})).status_code==401
    assert (await client.post('/api/v1/auth/login',json={'username_or_email':user.username,'password':'old-test-password'})).status_code==401
    new=await client.post('/api/v1/auth/login',json={'username_or_email':user.username,'password':'new-test-password'})
    assert new.status_code==200
    assert (await client.get('/api/v1/account',headers={'Authorization':'Bearer '+new.json()['access_token']})).status_code==200


@pytest.mark.asyncio
async def test_email_conflict_and_update(client,db_session):
    _,headers=await setup(db_session)
    payload={'current_password':'old-test-password','email':'other@example.com'}
    assert (await client.post('/api/v1/account/email',json=payload,headers=headers)).status_code==409
    assert (await client.get('/api/v1/account',headers=headers)).status_code==200
    payload['email']='updated@example.com'
    assert (await client.post('/api/v1/account/email',json=payload,headers=headers)).status_code==200
    assert (await client.get('/api/v1/account',headers=headers)).status_code==401


@pytest.mark.asyncio
async def test_reset_purpose_isolation_replay_and_session_revocation(client,db_session,sms_store):
    user,headers=await setup(db_session)
    assert (await client.post('/api/v1/auth/sms/send',json={'phone':user.username,'purpose':'login'})).status_code==200
    payload={'phone':user.username,'code':'123456','password':'reset-test-password'}
    assert (await client.post('/api/v1/auth/password/reset',json=payload)).status_code==400
    await sms_store.delete(sms_auth.key('cooldown',user.username))
    assert (await client.post('/api/v1/auth/sms/send',json={'phone':user.username,'purpose':'reset'})).status_code==200
    sms_auth.sms.verify.return_value=False
    assert (await client.post('/api/v1/auth/password/reset',json=payload)).status_code==400
    sms_auth.sms.verify.return_value=True
    assert (await client.post('/api/v1/auth/password/reset',json=payload)).status_code==200
    assert (await client.post('/api/v1/auth/password/reset',json=payload)).status_code==400
    assert (await client.get('/api/v1/account',headers=headers)).status_code==401
    assert (await client.post('/api/v1/auth/login',json={'username_or_email':user.username,'password':'reset-test-password'})).status_code==200


@pytest.mark.asyncio
async def test_phone_binding_requires_login_password_and_bound_code(client,db_session,sms_store):
    user,headers=await setup(db_session)
    new='13900000009'
    assert (await client.post('/api/v1/auth/sms/send',json={'phone':new,'purpose':'bind_phone'})).status_code==401
    assert (await client.post('/api/v1/auth/sms/send',json={'phone':new,'purpose':'bind_phone'},headers=headers)).status_code==200
    payload={'phone':new,'code':'123456','current_password':'incorrect-password'}
    assert (await client.post('/api/v1/account/phone',json=payload,headers=headers)).status_code==400
    payload['current_password']='old-test-password'
    assert (await client.post('/api/v1/account/phone',json=payload,headers=headers)).status_code==200
    assert (await client.get('/api/v1/account',headers=headers)).status_code==401
    result=await client.post('/api/v1/auth/login',json={'username_or_email':new,'password':'old-test-password'})
    assert result.status_code==200
    assert (await client.get('/api/v1/auth/me',headers={'Authorization':'Bearer '+result.json()['access_token']})).json()['id']==user.id

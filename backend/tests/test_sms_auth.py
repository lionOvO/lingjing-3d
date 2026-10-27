"""Run with an isolated disposable Redis; never send real SMS or use user data."""
import asyncio
import os
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from redis.asyncio import Redis

from app import sms_auth as auth
from app.models import User
from app.security import hash_password
from sqlalchemy import select, func


@pytest_asyncio.fixture
async def sms_store(monkeypatch):
    url = os.environ.get('SMS_TEST_REDIS_URL')
    if not url:
        pytest.skip('Requires disposable SMS_TEST_REDIS_URL')
    monkeypatch.setattr(auth.settings, 'redis_url', url)
    monkeypatch.setattr(auth.sms, 'configured', lambda: True)
    monkeypatch.setattr(auth.sms, 'send', AsyncMock())
    monkeypatch.setattr(auth.sms, 'verify', AsyncMock(return_value=True))
    async with Redis.from_url(url, decode_responses=True) as store:
        await store.flushdb()  # Only the explicitly supplied disposable test Redis.
        yield store


async def account(db):
    user = User(username='13900000001', email='sms@example.com', password_hash=hash_password('test-password'))
    db.add(user); await db.commit(); await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_login_existing_account_and_replay(client, db_session, sms_store):
    user = await account(db_session)
    data = {'phone':user.username}
    sent = await client.post('/api/v1/auth/sms/send', json=data)
    assert sent.status_code == 200 and sent.json()['retry_after'] == 60
    assert 'code' not in sent.json()
    data['code'] = '123456'
    login = await client.post('/api/v1/auth/login/phone', json=data)
    assert login.status_code == 200
    me = await client.get('/api/v1/auth/me', headers={'Authorization': 'Bearer '+login.json()['access_token']})
    assert me.json()['id'] == user.id
    assert (await client.post('/api/v1/auth/login/phone', json=data)).status_code == 400
    password = await client.post('/api/v1/auth/login', json={'username_or_email':user.username,'password':'test-password'})
    assert password.status_code == 200


@pytest.mark.asyncio
async def test_validation_unknown_account_and_missing_config(client, sms_store, monkeypatch):
    assert (await client.post('/api/v1/auth/sms/send', json={'phone':'invalid'})).status_code == 422
    assert (await client.post('/api/v1/auth/login/phone', json={'phone':'13900000001','code':'abcdef'})).status_code == 422
    assert (await client.post('/api/v1/auth/sms/send', json={'phone':'13900000002'})).status_code == 200
    auth.sms.send.assert_not_awaited()
    assert (await client.post('/api/v1/auth/login/phone', json={'phone':'13900000002','code':'123456'})).status_code == 400
    monkeypatch.setattr(auth.sms, 'configured', lambda: False)
    assert (await client.get('/api/v1/auth/options')).json()['sms_available'] is False
    assert (await client.post('/api/v1/auth/sms/send', json={'phone':'13900000001'})).status_code == 503


@pytest.mark.asyncio
async def test_concurrent_sends_and_cooldown(client, db_session, sms_store):
    user = await account(db_session)
    results = await asyncio.gather(*[client.post('/api/v1/auth/sms/send', json={'phone':user.username}) for _ in range(4)])
    assert sorted(r.status_code for r in results) == [200,429,429,429]
    auth.sms.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_wrong_attempts_expiry_and_provider_failure(client, db_session, sms_store, monkeypatch):
    user = await account(db_session)
    data = {'phone':user.username}
    auth.sms.send.side_effect = auth.HTTPException(503, 'provider unavailable')
    assert (await client.post('/api/v1/auth/sms/send', json=data)).status_code == 503
    assert (await client.post('/api/v1/auth/sms/send', json=data)).status_code == 429
    assert await sms_store.hget(auth.key('challenge', user.username), 'ready') == '0'
    await sms_store.flushdb()
    auth.sms.send.side_effect = None
    await client.post('/api/v1/auth/sms/send', json=data)
    auth.sms.verify.return_value = False
    data['code'] = '123456'
    for _ in range(6):
        assert (await client.post('/api/v1/auth/login/phone', json=data)).status_code == 400
    assert auth.sms.verify.await_count == 5
    auth.sms.verify.return_value = True
    assert (await client.post('/api/v1/auth/login/phone', json=data)).status_code == 400
    await sms_store.delete(auth.key('challenge', user.username))
    assert (await client.post('/api/v1/auth/login/phone', json=data)).status_code == 400


@pytest.mark.asyncio
async def test_concurrent_verification_only_one_token(client, db_session, sms_store):
    user = await account(db_session)
    await client.post('/api/v1/auth/sms/send', json={'phone':user.username})
    async def delayed(*args):
        await asyncio.sleep(.03)
        return True
    auth.sms.verify.side_effect = delayed
    results = await asyncio.gather(*[client.post('/api/v1/auth/login/phone', json={'phone':user.username,'code':'123456'}) for _ in range(3)])
    assert sorted(r.status_code for r in results) == [200,400,400]


@pytest.mark.asyncio
async def test_phone_and_ip_limits(client, db_session, sms_store):
    user = await account(db_session)
    await sms_store.set(auth.key('hour', user.username), 5, ex=3600)
    assert (await client.post('/api/v1/auth/sms/send', json={'phone':user.username})).status_code == 429
    await sms_store.flushdb()
    await sms_store.set(auth.key('day', user.username), 20, ex=86400)
    assert (await client.post('/api/v1/auth/sms/send', json={'phone':user.username})).status_code == 429
    await sms_store.flushdb()
    await sms_store.set(auth.key('ip', '127.0.0.1'), 10, ex=600)
    assert (await client.post('/api/v1/auth/sms/send', json={'phone':user.username})).status_code == 429
    auth.sms.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_signed_payload_and_error_redaction(monkeypatch):
    from pydantic import SecretStr
    monkeypatch.setattr(auth.settings, 'alibaba_cloud_access_key_id', SecretStr('test-id'))
    monkeypatch.setattr(auth.settings, 'alibaba_cloud_access_key_secret', SecretStr('test-secret'))
    monkeypatch.setattr(auth.settings, 'alibaba_sms_sign_name', 'test-sign')
    monkeypatch.setattr(auth.settings, 'alibaba_sms_template_code', 'test-template')
    seen = []
    async def post(self, url, **kwargs):
        seen.append(kwargs['data'])
        return httpx.Response(200,json={'Code':'OK','Success':True,'Model':{'VerifyResult':'PASS'}})
    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    service = auth.AliyunSMS()
    await service.send('13900000001')
    assert seen[-1]['ReturnVerifyCode'] == 'false' and seen[-1]['AutoRetry'] == '0'
    assert seen[-1]['ValidTime'] == '300' and seen[-1]['Signature']
    assert await service.verify('13900000001','123456') is True
    async def failure(self, url, **kwargs):
        return httpx.Response(400,json={'Code':'DENIED','Message':'test-secret sensitive-provider-data'})
    monkeypatch.setattr(httpx.AsyncClient, 'post', failure)
    with pytest.raises(auth.HTTPException) as error:
        await service.verify('13900000001','123456')
    assert 'test-secret' not in str(error.value.detail)


@pytest.mark.asyncio
async def test_verified_registration_then_both_login_methods(client, db_session, sms_store):
    phone = '13900000009'
    sent = await client.post('/api/v1/auth/sms/send', json={'phone':phone,'purpose':'register'})
    assert sent.status_code == 200
    auth.sms.send.assert_awaited_once_with(phone)
    assert await sms_store.hget(auth.key('challenge', phone), 'purpose') == 'register'
    # A registration code cannot log in, even if the provider would accept it.
    assert (await client.post('/api/v1/auth/login/phone', json={'phone':phone,'code':'123456'})).status_code == 400
    auth.sms.verify.assert_not_awaited()
    payload = {'phone':phone,'code':'123456','email':'new-sms@example.com','password':'new-test-password'}
    created = await client.post('/api/v1/auth/register', json=payload)
    assert created.status_code == 201
    assert created.json()['username'] == phone and 'password_hash' not in created.json()
    user = await db_session.scalar(select(User).where(User.username == phone))
    assert user.password_hash != payload['password']
    assert not await sms_store.exists(auth.key('challenge', phone))
    assert (await client.post('/api/v1/auth/register', json=payload)).status_code == 409
    password = await client.post('/api/v1/auth/login', json={'username_or_email':phone,'password':payload['password']})
    assert password.status_code == 200
    assert (await client.post('/api/v1/auth/login', json={'username_or_email':payload['email'],'password':payload['password']})).status_code == 200
    await sms_store.delete(auth.key('cooldown', phone))
    assert (await client.post('/api/v1/auth/sms/send', json={'phone':phone,'purpose':'login'})).status_code == 200
    login = await client.post('/api/v1/auth/login/phone', json={'phone':phone,'code':'123456'})
    assert login.status_code == 200
    me = await client.get('/api/v1/auth/me',headers={'Authorization':'Bearer '+login.json()['access_token']})
    assert me.json()['id'] == created.json()['id']


@pytest.mark.asyncio
async def test_registration_cannot_skip_or_reuse_login_verification(client, db_session, sms_store):
    payload = {'phone':'13900000008','email':'not-created@example.com','password':'new-test-password'}
    assert (await client.post('/api/v1/auth/register',json=payload)).status_code == 422
    assert (await client.post('/api/v1/auth/register',json={**payload,'code':'123456'})).status_code == 400
    assert (await client.post('/api/v1/auth/register',json={'username':'unverified','email':payload['email'],'password':payload['password']})).status_code == 422
    assert (await client.post('/api/v1/users',json={'username':payload['phone'],'email':payload['email'],'password_hash':'arbitrary-client-hash'})).status_code == 410
    assert await db_session.scalar(select(func.count()).select_from(User)) == 0
    await client.post('/api/v1/auth/sms/send',json={'phone':payload['phone'],'purpose':'register'})
    # Bind the local record to login to ensure registration rejects the other purpose.
    await sms_store.hset(auth.key('challenge',payload['phone']),'purpose','login')
    assert (await client.post('/api/v1/auth/register',json={**payload,'code':'123456'})).status_code == 400
    auth.sms.verify.assert_not_awaited()


@pytest.mark.asyncio
async def test_register_errors_never_create_account(client, db_session, sms_store):
    phone='13900000007'
    await client.post('/api/v1/auth/sms/send',json={'phone':phone,'purpose':'register'})
    payload={'phone':phone,'code':'123456','email':'wrong-code@example.com','password':'new-test-password'}
    auth.sms.verify.return_value=False
    assert (await client.post('/api/v1/auth/register',json=payload)).status_code == 400
    auth.sms.verify.return_value=True
    await sms_store.expire(auth.key('challenge',phone),0)
    assert (await client.post('/api/v1/auth/register',json=payload)).status_code == 400
    assert await db_session.scalar(select(func.count()).select_from(User)) == 0


@pytest.mark.asyncio
async def test_registered_phone_and_email_conflicts(client, db_session, sms_store):
    user=await account(db_session)
    assert (await client.post('/api/v1/auth/sms/send',json={'phone':user.username,'purpose':'register'})).status_code == 409
    auth.sms.send.assert_not_awaited()
    payload={'phone':'13900000006','code':'123456','email':user.email,'password':'new-test-password'}
    assert (await client.post('/api/v1/auth/register',json=payload)).status_code == 409
    auth.sms.verify.assert_not_awaited()
    assert await db_session.scalar(select(func.count()).select_from(User)) == 1


@pytest.mark.asyncio
async def test_registration_concurrent_submit_creates_only_one_user(client, db_session, sms_store):
    phone='13900000005'
    await client.post('/api/v1/auth/sms/send',json={'phone':phone,'purpose':'register'})
    async def delayed(*args):
        await asyncio.sleep(.03)
        return True
    auth.sms.verify.side_effect=delayed
    payload={'phone':phone,'code':'123456','email':'concurrent@example.com','password':'new-test-password'}
    results=await asyncio.gather(*[client.post('/api/v1/auth/register',json=payload) for _ in range(3)])
    assert [r.status_code for r in results].count(201) == 1
    assert all(r.status_code in {201,400,409} for r in results)
    assert await db_session.scalar(select(func.count()).select_from(User)) == 1


@pytest.mark.asyncio
async def test_purposes_share_cooldown_and_registration_rejects_unknown_purpose(client, sms_store):
    phone='13900000004'
    assert (await client.post('/api/v1/auth/sms/send',json={'phone':phone,'purpose':'unknown'})).status_code == 422
    assert (await client.post('/api/v1/auth/sms/send',json={'phone':phone,'purpose':'register'})).status_code == 200
    assert (await client.post('/api/v1/auth/sms/send',json={'phone':phone,'purpose':'login'})).status_code == 429
    auth.sms.send.assert_awaited_once()

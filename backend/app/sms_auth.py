"""Purpose-bound PNVS login and registration; no client-side/test codes."""
import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone
from urllib.parse import quote
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from .config import settings
from .database import get_db_session
from .models import User, AccountProfile
from .schemas import TokenResponse, AuthRegister, UserRead
from .security import create_access_token, create_refresh_token, hash_password, account_version, get_current_user, bearer

router = APIRouter(prefix="/api/v1/auth")


class PhoneInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    phone: str = Field(pattern=r"^1[3-9][0-9]{9}$")


class CodeInput(PhoneInput):
    code: str = Field(pattern=r"^[0-9]{6}$")


class SendInput(PhoneInput):
    purpose: Literal["login", "register", "reset", "bind_phone"] = "login"


class AliyunSMS:
    def configured(self):
        return all((settings.alibaba_cloud_access_key_id.get_secret_value(),
                    settings.alibaba_cloud_access_key_secret.get_secret_value(),
                    settings.alibaba_sms_sign_name, settings.alibaba_sms_template_code))

    async def call(self, action, **fields):
        if not self.configured():
            raise HTTPException(503, "短信服务尚未配置，请使用密码登录")
        params = dict(Action=action, Version="2017-05-25", RegionId=settings.alibaba_sms_region,
                      CountryCode="86", Format="JSON",
                      AccessKeyId=settings.alibaba_cloud_access_key_id.get_secret_value(),
                      SignatureMethod="HMAC-SHA1", SignatureVersion="1.0",
                      SignatureNonce=secrets.token_hex(16),
                      Timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **fields)
        if settings.alibaba_sms_scheme_name:
            params["SchemeName"] = settings.alibaba_sms_scheme_name
        encode = lambda value: quote(str(value), safe="~")
        canonical = "&".join(f"{encode(k)}={encode(params[k])}" for k in sorted(params))
        signature = hmac.new((settings.alibaba_cloud_access_key_secret.get_secret_value() + "&").encode(),
                             ("POST&%2F&" + encode(canonical)).encode(), hashlib.sha1).digest()
        params["Signature"] = base64.b64encode(signature).decode()
        try:
            async with httpx.AsyncClient(timeout=10, trust_env=False, follow_redirects=False) as client:
                response = await client.post("https://dypnsapi.aliyuncs.com/", data=params)
                payload = response.json()
        except (httpx.HTTPError, ValueError):
            raise HTTPException(503, "短信服务暂不可用，请稍后重试或使用密码登录") from None
        if not isinstance(payload, dict) or not isinstance(payload.get("Model", {}), dict):
            raise HTTPException(503, "短信服务响应异常，请使用密码登录")
        if response.status_code != 200 or payload.get("Code") != "OK" or payload.get("Success") is False:
            if payload.get("Code") in {"FREQUENCY_FAIL", "isv.BUSINESS_LIMIT_CONTROL"}:
                raise HTTPException(429, "获取验证码过于频繁，请稍后重试")
            # Never expose the provider response, phone, signature or access key.
            raise HTTPException(503, "短信服务调用失败，请联系管理员检查签名、模板和权限")
        return payload.get("Model", {})

    async def send(self, phone):
        await self.call("SendSmsVerifyCode", PhoneNumber=phone, SignName=settings.alibaba_sms_sign_name,
                        TemplateCode=settings.alibaba_sms_template_code,
                        TemplateParam=json.dumps({"code": "##code##", "min": "5"}), CodeLength="6",
                        CodeType="1", ValidTime="300", Interval="60", DuplicatePolicy="1",
                        ReturnVerifyCode="false", AutoRetry="0", OutId="lingjing_" + secrets.token_hex(16))

    async def verify(self, phone, code):
        return (await self.call("CheckSmsVerifyCode", PhoneNumber=phone, VerifyCode=code,
                                CaseAuthPolicy="1")).get("VerifyResult") == "PASS"


sms = AliyunSMS()


async def get_store():
    try:
        async with Redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=3,
                                  socket_connect_timeout=3) as store:
            yield store
    except RedisError:
        raise HTTPException(503, "验证码校验服务暂不可用，请使用密码登录") from None


def key(kind, value):
    digest = hmac.new(settings.jwt_secret.encode(), value.encode(), hashlib.sha256).hexdigest()
    return f"lingjing:sms:v1:{kind}:{digest}"


# Reservation, rate checks and counters must be atomic across API workers.
RESERVE = """
if redis.call('EXISTS',KEYS[1]) == 1 then return 0 end
for i=3,5 do
  if tonumber(redis.call('GET',KEYS[i]) or '0') >= tonumber(ARGV[i-1]) then return -1 end
end
redis.call('SET',KEYS[1],'1','EX',60)
local ttl={3600,86400,600}
for i=3,5 do
  if redis.call('INCR',KEYS[i]) == 1 then redis.call('EXPIRE',KEYS[i],ttl[i-2]) end
end
redis.call('DEL',KEYS[2])
redis.call('HSET',KEYS[2],'id',ARGV[1],'ready',0,'attempts',0,'purpose',ARGV[5])
redis.call('EXPIRE',KEYS[2],300)
return 1
"""
READY = """
if redis.call('HGET',KEYS[1],'id') == ARGV[1] then
  redis.call('HSET',KEYS[1],'ready',1) return 1
end
return 0
"""
BEGIN_VERIFY = """
if redis.call('HGET',KEYS[1],'purpose') ~= ARGV[1] then return '' end
if redis.call('HGET',KEYS[1],'ready') ~= '1' then return '' end
if tonumber(redis.call('HGET',KEYS[1],'attempts') or '5') >= 5 then return '' end
redis.call('HINCRBY',KEYS[1],'attempts',1)
redis.call('HSET',KEYS[1],'ready',0)
return redis.call('HGET',KEYS[1],'id')
"""
FINISH_VERIFY = """
if redis.call('HGET',KEYS[1],'id') ~= ARGV[1] then return 0 end
if ARGV[2] == '1' then redis.call('DEL',KEYS[1])
else redis.call('HSET',KEYS[1],'ready',1) end
return 1
"""


@router.get("/options")
async def options():
    return {"sms_available": bool(sms.configured()), "expires_in": 300, "retry_after": 60}


@router.post("/sms/send")
async def send_code(data: SendInput, request: Request, store=Depends(get_store),
                    db: AsyncSession = Depends(get_db_session), credentials=Depends(bearer)):
    if data.purpose == "bind_phone":
        await get_current_user(credentials, db)
    if not sms.configured():
        raise HTTPException(503, "短信服务尚未配置，请使用密码登录")
    # Do not trust X-Forwarded-For supplied by callers. Proxy deployments share the IP quota.
    ip = request.client.host if request.client else "unknown"
    challenge = key("challenge", data.phone)
    nonce = secrets.token_hex(16)
    reserved = await store.eval(RESERVE, 5, key("cooldown", data.phone), challenge,
                                key("hour", data.phone), key("day", data.phone), key("ip", ip),
                                nonce, 5, 20, 10, data.purpose)
    if reserved != 1:
        raise HTTPException(429, "请等待 60 秒后重试，或稍后再获取验证码", headers={"Retry-After": "60"})
    account = await db.scalar(select(User.id).where(User.username == data.phone))
    if data.purpose in {"register", "bind_phone"} and account is not None:
        raise HTTPException(409, "该手机号已注册，请直接登录")
    if account is not None or data.purpose in {"register", "bind_phone"}:
        # A failed/uncertain send retains the cooldown; never replay paid SMS automatically.
        await sms.send(data.phone)
        if not await store.eval(READY, 1, challenge, nonce):
            raise HTTPException(503, "验证码发送状态已失效，请稍后重新获取")
    # Use the same response for unregistered numbers without spending an SMS.
    return {"message": "验证码已发送，请查看手机短信" if data.purpose in {"register", "bind_phone"} else "若该手机号已注册，验证码将发送至手机，请查看短信", "expires_in": 300, "retry_after": 60}


async def verify_code(phone: str, code: str, purpose: str, store):
    if not sms.configured():
        raise HTTPException(503, "短信服务尚未配置，请使用密码登录")
    challenge = key("challenge", phone)
    nonce = await store.eval(BEGIN_VERIFY, 1, challenge, purpose)
    if not nonce:
        raise HTTPException(400, "验证码已失效或尝试次数过多，请重新获取")
    passed = False
    try:
        passed = await sms.verify(phone, code)
    finally:
        fresh = await store.eval(FINISH_VERIFY, 1, challenge, nonce, "1" if passed else "0")
    if not passed or not fresh:
        raise HTTPException(400, "验证码不正确或已失效，请重新获取")


@router.post("/login/phone", response_model=TokenResponse)
async def login_phone(data: CodeInput, store=Depends(get_store), db: AsyncSession = Depends(get_db_session)):
    await verify_code(data.phone, data.code, "login", store)
    user = await db.scalar(select(User).where(User.username == data.phone))
    if user is None:
        raise HTTPException(400, "账号不存在，请使用已有账号登录")
    version = await account_version(db, user.id)
    return TokenResponse(access_token=create_access_token(user.id, version), refresh_token=create_refresh_token(user.id, version),
                         expires_in=settings.access_token_expire_minutes * 60)


@router.post("/register", response_model=UserRead, status_code=201)
async def register(data: AuthRegister, store=Depends(get_store), db: AsyncSession = Depends(get_db_session)):
    if await db.scalar(select(User.id).where((User.username == data.phone) | (User.email == str(data.email)))):
        raise HTTPException(409, "手机号或邮箱已注册，请登录或更换邮箱")
    await verify_code(data.phone, data.code, "register", store)
    user = User(username=data.phone, email=str(data.email), password_hash=hash_password(data.password),
                avatar_url=str(data.avatar_url) if data.avatar_url else None)
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "手机号或邮箱已注册，请直接登录") from None
    await db.refresh(user)
    return user


class ResetInput(CodeInput):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    password: str = Field(min_length=8, max_length=128)


@router.post("/password/reset")
async def reset_password(data: ResetInput, store=Depends(get_store), db: AsyncSession = Depends(get_db_session)):
    await verify_code(data.phone, data.code, "reset", store)
    user = await db.scalar(select(User).where(User.username == data.phone).with_for_update())
    if not user:
        raise HTTPException(400, "手机号或验证码无效")
    profile = await db.get(AccountProfile, user.id)
    if profile is None:
        profile = AccountProfile(user_id=user.id, display_name="", token_version=0)
        db.add(profile)
    user.password_hash = hash_password(data.password)
    profile.token_version += 1
    await db.commit()
    return {"message": "密码已重设，请重新登录；其他设备的登录状态已失效"}

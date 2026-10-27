"""Self-service account changes. Security changes invalidate all JWT sessions."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field, HttpUrl, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_db_session
from .models import AccountProfile, User
from .schemas import UserRead
from .security import get_current_user, hash_password, verify_password
from .sms_auth import CodeInput, get_store, verify_code

router = APIRouter(prefix="/api/v1/account", tags=["account"])


class ProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=1, max_length=40)
    avatar_url: HttpUrl | None = None


class PasswordInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=8, max_length=128)
    password: str = Field(min_length=8, max_length=128)


class EmailInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr = Field(max_length=100)
    current_password: str = Field(min_length=8, max_length=128)


class PhoneChange(CodeInput):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    current_password: str = Field(min_length=8, max_length=128)


async def lock_user(db, user):
    return await db.scalar(select(User).where(User.id == user.id).with_for_update().execution_options(populate_existing=True))


async def profile_for(db, user):
    profile = await db.get(AccountProfile, user.id)
    if profile is None:
        profile = AccountProfile(user_id=user.id, display_name="", token_version=0)
        db.add(profile)
    return profile


def check_password(user, password):
    if not verify_password(password, user.password_hash):
        raise HTTPException(400, "当前密码不正确，请检查后重试")


@router.get("")
async def account(user=Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    profile = await db.get(AccountProfile, user.id)
    return {**UserRead.model_validate(user).model_dump(), "display_name": profile.display_name if profile else "",
            "phone": user.username if user.username.isdigit() and len(user.username) == 11 else None,
            "email_verified": False}


@router.patch("/profile")
async def save_profile(data: ProfileInput, user=Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    if not data.display_name.strip():
        raise HTTPException(422, "昵称不能为空")
    user = await lock_user(db, user)
    profile = await profile_for(db, user)
    profile.display_name = data.display_name.strip()
    user.avatar_url = str(data.avatar_url) if data.avatar_url else None
    await db.commit()
    return {"message": "个人资料已保存"}


@router.post("/password")
async def password(data: PasswordInput, user=Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    user = await lock_user(db, user)
    check_password(user, data.current_password)
    if verify_password(data.password, user.password_hash):
        raise HTTPException(400, "新密码不能与当前密码相同")
    user.password_hash = hash_password(data.password)
    profile = await profile_for(db, user)
    profile.token_version += 1
    await db.commit()
    return {"message": "密码已修改，请重新登录；其他设备的登录状态已失效"}


@router.post("/email")
async def email(data: EmailInput, user=Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    user = await lock_user(db, user)
    check_password(user, data.current_password)
    user.email = str(data.email)
    profile = await profile_for(db, user)
    profile.token_version += 1
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "该邮箱已被使用") from None
    return {"message": "联系邮箱已更新，请重新登录。此邮箱尚未验证，不用于短信找回"}


@router.post("/phone")
async def phone(data: PhoneChange, user=Depends(get_current_user), store=Depends(get_store), db: AsyncSession = Depends(get_db_session)):
    user = await lock_user(db, user)
    check_password(user, data.current_password)
    if await db.scalar(select(User.id).where(User.username == data.phone)):
        raise HTTPException(409, "该手机号已被使用")
    await verify_code(data.phone, data.code, "bind_phone", store)
    user.username = data.phone
    profile = await profile_for(db, user)
    profile.token_version += 1
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "该手机号已被使用") from None
    return {"message": "手机号已更新，请使用新手机号重新登录"}

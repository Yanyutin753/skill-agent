"""User personalization settings API - PostgreSQL storage."""

import json
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

import asyncpg
from fastapi_agent.core.config import settings


router = APIRouter()

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            database=settings.POSTGRES_DB,
            min_size=1,
            max_size=5,
        )
        await _init_schema()
    return _pool


async def _init_schema():
    pool = _pool
    if not pool:
        return
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_personalization (
                user_id VARCHAR(255) PRIMARY KEY,
                settings JSONB NOT NULL DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


class CommunicationStyle(BaseModel):
    tone: str = Field(default="专业")
    verbosity: str = Field(default="适中")
    language: str = Field(default="中文")


class UserProfile(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    expertise_level: str = Field(default="中级")
    industry: Optional[str] = None


class TechPreferences(BaseModel):
    preferred_languages: list[str] = Field(default_factory=list)
    preferred_frameworks: list[str] = Field(default_factory=list)
    coding_style: Optional[str] = None


class PersonalizationSettings(BaseModel):
    user_id: str
    style: CommunicationStyle = Field(default_factory=CommunicationStyle)
    profile: UserProfile = Field(default_factory=UserProfile)
    tech: TechPreferences = Field(default_factory=TechPreferences)
    custom_instructions: Optional[str] = None

    def to_prompt(self) -> str:
        parts = []
        if self.profile.name:
            parts.append(f"用户称呼: {self.profile.name}")
        if self.profile.role:
            parts.append(f"职业角色: {self.profile.role}")
        if self.profile.expertise_level:
            parts.append(f"技术水平: {self.profile.expertise_level}")
        if self.profile.industry:
            parts.append(f"所属行业: {self.profile.industry}")
        parts.append(f"沟通风格: {self.style.tone}")
        parts.append(f"详细程度: {self.style.verbosity}")
        parts.append(f"首选语言: {self.style.language}")
        if self.tech.preferred_languages:
            parts.append(f"偏好语言: {', '.join(self.tech.preferred_languages)}")
        if self.tech.preferred_frameworks:
            parts.append(f"偏好框架: {', '.join(self.tech.preferred_frameworks)}")
        if self.tech.coding_style:
            parts.append(f"编码风格: {self.tech.coding_style}")
        if self.custom_instructions:
            parts.append(f"\n自定义指令:\n{self.custom_instructions}")
        return "\n".join(parts)


class PersonalizationResponse(BaseModel):
    success: bool
    settings: Optional[PersonalizationSettings] = None
    message: Optional[str] = None


@router.get("/settings/{user_id}", response_model=PersonalizationResponse)
async def get_personalization(user_id: str):
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT settings FROM user_personalization WHERE user_id = $1",
                user_id
            )
            if row:
                data = json.loads(row["settings"]) if isinstance(row["settings"], str) else row["settings"]
                data["user_id"] = user_id
                return PersonalizationResponse(success=True, settings=PersonalizationSettings(**data))
        return PersonalizationResponse(
            success=True,
            settings=PersonalizationSettings(user_id=user_id),
            message="Using default settings",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/settings", response_model=PersonalizationResponse)
async def save_personalization(req_settings: PersonalizationSettings):
    try:
        pool = await get_pool()
        data = req_settings.model_dump(exclude={"user_id"})
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO user_personalization (user_id, settings, updated_at)
                VALUES ($1, $2, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id) DO UPDATE SET
                    settings = $2,
                    updated_at = CURRENT_TIMESTAMP
            """, req_settings.user_id, json.dumps(data, ensure_ascii=False))
        return PersonalizationResponse(success=True, settings=req_settings, message="Settings saved")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/settings/{user_id}", response_model=PersonalizationResponse)
async def reset_personalization(user_id: str):
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM user_personalization WHERE user_id = $1",
                user_id
            )
        return PersonalizationResponse(
            success=True,
            settings=PersonalizationSettings(user_id=user_id),
            message="Settings reset",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


STYLE_PRESETS = {
    "professional": {
        "name": "专业严谨",
        "description": "适合工作场景，输出正式、精确",
        "style": {"tone": "专业", "verbosity": "适中", "language": "中文"},
    },
    "casual": {
        "name": "轻松随意",
        "description": "日常对话风格，更自然亲和",
        "style": {"tone": "随意", "verbosity": "简洁", "language": "中文"},
    },
    "detailed": {
        "name": "详尽解释",
        "description": "提供详细说明和背景知识",
        "style": {"tone": "友好", "verbosity": "详细", "language": "中文"},
    },
    "code_focused": {
        "name": "代码优先",
        "description": "减少解释，直接给出代码",
        "style": {"tone": "专业", "verbosity": "简洁", "language": "英文"},
    },
}

ROLE_PRESETS = {
    "developer": {"name": "开发者", "expertise_level": "中级"},
    "senior_developer": {"name": "高级开发者", "expertise_level": "专家"},
    "designer": {"name": "设计师", "expertise_level": "中级"},
    "manager": {"name": "项目经理", "expertise_level": "中级"},
    "student": {"name": "学生", "expertise_level": "入门"},
    "researcher": {"name": "研究员", "expertise_level": "专家"},
}


@router.get("/presets")
async def get_presets():
    return {"styles": STYLE_PRESETS, "roles": ROLE_PRESETS}


def get_user_personalization(user_id: str) -> PersonalizationSettings | None:
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, _get_user_personalization_async(user_id))
                return future.result(timeout=5)
        else:
            return asyncio.run(_get_user_personalization_async(user_id))
    except Exception:
        return None


async def _get_user_personalization_async(user_id: str) -> PersonalizationSettings | None:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT settings FROM user_personalization WHERE user_id = $1",
                user_id
            )
            if row:
                data = json.loads(row["settings"]) if isinstance(row["settings"], str) else row["settings"]
                data["user_id"] = user_id
                return PersonalizationSettings(**data)
    except Exception:
        pass
    return None

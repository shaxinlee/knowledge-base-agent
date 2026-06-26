import json
import os
from pathlib import Path

from pydantic import ValidationError

from app.core.config import get_settings
from app.core.errors import ApiError
from app.schemas.assistant_profile import (
    AssistantProfileResponse,
    AssistantProfileUpdateRequest,
)


DEFAULT_ASSISTANT_PROFILE = AssistantProfileResponse(
    name="知识库问答助手",
    identity_answer="我是你的知识库问答助手，可以基于已接入的文档、制度、产品资料和业务知识回答问题。",
    capability_answer="我可以帮你查询知识库内容、总结文档、解释流程、定位相关资料，并在答案中给出引用来源。",
    greeting_answer="你好，我是知识库问答助手。你可以直接提问需要查询的制度、流程、产品资料或业务知识。",
    thanks_answer="不客气，有需要查询知识库内容时可以继续问我。",
    usage_answer=(
        "你可以直接输入问题，我会判断是否需要检索知识库；"
        "如果需要，我会基于已接入资料回答并给出引用来源。"
    ),
    handoff_answer="当前我无法直接转接人工客服。你可以联系系统管理员或相关业务负责人处理人工支持需求。",
    fallback_casual_answer=(
        "我是知识库问答助手，更擅长回答已接入资料中的制度、流程、产品和业务知识问题。"
    ),
)


def get_assistant_profile() -> AssistantProfileResponse:
    path = get_assistant_profile_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return DEFAULT_ASSISTANT_PROFILE
        merged = {**DEFAULT_ASSISTANT_PROFILE.model_dump(), **payload}
        return AssistantProfileResponse.model_validate(merged)
    except (OSError, json.JSONDecodeError, ValidationError):
        return DEFAULT_ASSISTANT_PROFILE


def update_assistant_profile(
    payload: AssistantProfileUpdateRequest,
) -> AssistantProfileResponse:
    profile = AssistantProfileResponse.model_validate(
        {key: value.strip() for key, value in payload.model_dump().items()}
    )
    path = get_assistant_profile_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        temp_path.write_text(
            json.dumps(profile.model_dump(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temp_path, path)
    except OSError as exc:
        raise ApiError(
            code="CONFIG_WRITE_FAILED",
            message="Assistant profile configuration could not be saved.",
            status_code=500,
            details={"path": str(path)},
        ) from exc
    return profile


def get_profile_answer(category: str) -> str | None:
    profile = get_assistant_profile()
    answer_by_category: dict[str, str] = {
        "identity": profile.identity_answer,
        "capability": profile.capability_answer,
        "greeting": profile.greeting_answer,
        "thanks": profile.thanks_answer,
        "usage": profile.usage_answer,
        "handoff": profile.handoff_answer,
        "casual": profile.fallback_casual_answer,
    }
    return answer_by_category.get(category)


def get_assistant_profile_path() -> Path:
    raw_path = Path(get_settings().assistant_profile_config_path)
    if raw_path.is_absolute():
        return raw_path
    app_root = Path(__file__).resolve().parents[1]
    if raw_path.parts and raw_path.parts[0] == "app":
        return app_root / Path(*raw_path.parts[1:])
    return app_root / raw_path

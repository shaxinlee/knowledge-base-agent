import json
import os
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.core.config import get_settings
from app.core.errors import ApiError
from app.schemas.model_settings import (
    ModelEndpointSettings,
    ModelSettingsResponse,
    ModelSettingsUpdateRequest,
)


def get_default_model_settings() -> ModelSettingsResponse:
    settings = get_settings()
    return ModelSettingsResponse(
        mineru=ModelEndpointSettings(
            base_url=settings.mineru_api_base_url,
            api_key=settings.mineru_api_token,
            model=settings.mineru_model_version,
        ),
        llm=ModelEndpointSettings(
            base_url=settings.llm_api_base_url.strip() or settings.llm_api_base,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
        ),
        text_embedding=ModelEndpointSettings(
            base_url=settings.embedding_api_base_url.strip() or settings.embedding_service_url,
            api_key=settings.embedding_api_key,
            model=settings.embedding_model,
        ),
        reranker=ModelEndpointSettings(
            base_url=settings.reranker_api_base_url.strip() or settings.reranker_service_url,
            api_key=settings.reranker_api_key,
            model=settings.reranker_model,
        ),
        intent_recognition=ModelEndpointSettings(
            base_url=(
                settings.intent_recognition_api_base_url.strip()
                or settings.llm_api_base_url.strip()
                or settings.llm_api_base
            ),
            api_key=settings.intent_recognition_api_key or settings.llm_api_key,
            model=settings.intent_recognition_model.strip() or settings.llm_model,
        ),
        knowledge_search_classifier=ModelEndpointSettings(
            base_url=(
                settings.knowledge_search_classifier_api_base_url.strip()
                or settings.intent_recognition_api_base_url.strip()
                or settings.llm_api_base_url.strip()
                or settings.llm_api_base
            ),
            api_key=(
                settings.knowledge_search_classifier_api_key
                or settings.intent_recognition_api_key
                or settings.llm_api_key
            ),
            model=settings.knowledge_search_classifier_model,
        ),
        image_description=ModelEndpointSettings(
            base_url=(
                settings.image_description_api_base_url.strip()
                or settings.llm_api_base_url.strip()
                or settings.llm_api_base
            ),
            api_key=settings.image_description_api_key or settings.llm_api_key,
            model=settings.image_description_model,
        ),
        multimodal_embedding=ModelEndpointSettings(
            base_url=settings.qwen_base_url,
            api_key=settings.qwen_api_key or settings.embedding_api_key,
            model=settings.qwen_embedding_model,
        ),
    )


def get_model_settings() -> ModelSettingsResponse:
    path = get_model_settings_path()
    defaults = get_default_model_settings()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return defaults
        merged = merge_model_settings(defaults.model_dump(), payload)
        return ModelSettingsResponse.model_validate(merged)
    except (OSError, json.JSONDecodeError, ValidationError):
        return defaults


def update_model_settings(payload: ModelSettingsUpdateRequest) -> ModelSettingsResponse:
    model_settings = ModelSettingsResponse.model_validate(
        {
            section: {
                key: value.strip()
                for key, value in section_payload.items()
            }
            for section, section_payload in payload.model_dump().items()
        }
    )
    path = get_model_settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        temp_path.write_text(
            json.dumps(model_settings.model_dump(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temp_path, path)
    except OSError as exc:
        raise ApiError(
            code="CONFIG_WRITE_FAILED",
            message="Model settings configuration could not be saved.",
            status_code=500,
            details={"path": str(path)},
        ) from exc
    return model_settings


def merge_model_settings(defaults: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    merged = dict(defaults)
    for section, value in payload.items():
        if isinstance(value, dict) and isinstance(merged.get(section), dict):
            section_defaults = dict(merged[section])
            section_defaults.update(value)
            merged[section] = section_defaults
        else:
            merged[section] = value
    return merged


def get_model_settings_path() -> Path:
    raw_path = Path(get_settings().model_settings_config_path)
    if raw_path.is_absolute():
        return raw_path
    app_root = Path(__file__).resolve().parents[1]
    if raw_path.parts and raw_path.parts[0] == "app":
        return app_root / Path(*raw_path.parts[1:])
    return app_root / raw_path

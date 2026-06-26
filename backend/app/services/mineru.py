from dataclasses import dataclass
from typing import Any, NoReturn, Protocol, cast

import httpx

from app.core.config import get_settings
from app.core.errors import ApiError
from app.services.model_settings import get_model_settings


@dataclass(frozen=True)
class MineruSubmission:
    batch_id: str
    data_id: str
    raw_response: dict[str, Any]


class MineruClient(Protocol):
    def submit_file(
        self,
        *,
        file_name: str,
        data_id: str,
        content: bytes,
    ) -> MineruSubmission: ...

    def get_batch_result(self, *, batch_id: str) -> dict[str, Any]: ...

    def download_result(self, *, url: str) -> bytes: ...


class MineruApiClient:
    def submit_file(
        self,
        *,
        file_name: str,
        data_id: str,
        content: bytes,
    ) -> MineruSubmission:
        settings = get_settings()
        model_settings = get_model_settings()
        mineru_settings = model_settings.mineru
        token = require_mineru_token()
        payload = {
            "enable_formula": settings.mineru_enable_formula,
            "enable_table": settings.mineru_enable_table,
            "language": settings.mineru_language,
            "model_version": mineru_settings.model or settings.mineru_model_version,
            "files": [
                {
                    "name": file_name,
                    "is_ocr": settings.mineru_is_ocr,
                    "data_id": data_id,
                }
            ],
        }
        response = httpx.post(
            build_mineru_url("/api/v4/file-urls/batch"),
            headers=build_auth_headers(token),
            json=payload,
            timeout=settings.mineru_request_timeout_seconds,
        )
        result = parse_mineru_json_response(response)
        data = get_response_data(result)
        batch_id = str(data.get("batch_id") or "")
        file_urls = data.get("file_urls")
        if not batch_id or not isinstance(file_urls, list) or not file_urls:
            raise_upstream_error("MinerU upload URL response is missing batch_id or file_urls.")
        first_file_url = str(file_urls[0])

        upload_response = httpx.put(
            first_file_url,
            content=content,
            timeout=settings.mineru_request_timeout_seconds,
        )
        if upload_response.status_code not in (200, 201):
            raise_upstream_error(
                f"MinerU signed upload failed with HTTP {upload_response.status_code}."
            )

        return MineruSubmission(batch_id=batch_id, data_id=data_id, raw_response=result)

    def get_batch_result(self, *, batch_id: str) -> dict[str, Any]:
        settings = get_settings()
        token = require_mineru_token()
        response = httpx.get(
            build_mineru_url(f"/api/v4/extract-results/batch/{batch_id}"),
            headers=build_auth_headers(token),
            timeout=settings.mineru_request_timeout_seconds,
        )
        return parse_mineru_json_response(response)

    def download_result(self, *, url: str) -> bytes:
        settings = get_settings()
        response = httpx.get(url, timeout=settings.mineru_request_timeout_seconds)
        if response.status_code != 200:
            raise_upstream_error(f"MinerU result download failed with HTTP {response.status_code}.")
        return bytes(response.content)


def get_mineru_client() -> MineruClient:
    return MineruApiClient()


def build_mineru_url(path: str) -> str:
    settings = get_settings()
    model_settings = get_model_settings()
    base_url = model_settings.mineru.base_url or settings.mineru_api_base_url
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def build_auth_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "*/*",
    }


def require_mineru_token() -> str:
    token = (get_model_settings().mineru.api_key or get_settings().mineru_api_token).strip()
    if not token:
        raise_upstream_error("MinerU API token is not configured.")
    return token


def parse_mineru_json_response(response: httpx.Response) -> dict[str, Any]:
    if response.status_code != 200:
        raise_upstream_error(f"MinerU API returned HTTP {response.status_code}.")
    try:
        result = response.json()
    except ValueError:
        raise_upstream_error("MinerU API returned a non-JSON response.")
    if not isinstance(result, dict):
        raise_upstream_error("MinerU API returned an invalid JSON response.")
    if result.get("code") != 0:
        message = result.get("msg") or "MinerU API request failed."
        raise_upstream_error(str(message))
    return result


def get_response_data(result: dict[str, Any]) -> dict[str, Any]:
    data = result.get("data")
    if not isinstance(data, dict):
        raise_upstream_error("MinerU API response data is missing.")
    return cast(dict[str, Any], data)


def extract_first_result(batch_result: dict[str, Any], *, data_id: str) -> dict[str, Any] | None:
    data = batch_result.get("data")
    if not isinstance(data, dict):
        return None
    extract_result = data.get("extract_result")
    if isinstance(extract_result, dict):
        return extract_result
    if not isinstance(extract_result, list):
        return None

    for item in extract_result:
        if isinstance(item, dict) and str(item.get("data_id") or "") == data_id:
            return item
    for item in extract_result:
        if isinstance(item, dict):
            return item
    return None


def raise_upstream_error(message: str) -> NoReturn:
    raise ApiError(
        code="UPSTREAM_SERVICE_ERROR",
        message=message,
        status_code=503,
    )

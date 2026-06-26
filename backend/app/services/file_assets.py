import mimetypes
import posixpath
import zipfile
from dataclasses import dataclass
from io import BytesIO
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models import File, ParseJob
from app.services.document_blocks import get_parsed_result_location
from app.services.object_storage import ObjectStorage


@dataclass(frozen=True)
class FileAsset:
    content: bytes
    media_type: str


def get_raw_file_asset(
    db: Session,
    *,
    file_id: UUID,
    storage: ObjectStorage,
) -> FileAsset:
    file = require_existing_file(db, file_id=file_id)
    return FileAsset(
        content=storage.get_object(bucket=file.storage_bucket, key=file.storage_key),
        media_type=file.mime_type or guess_media_type(file.file_name),
    )


def get_parsed_file_asset(
    db: Session,
    *,
    file_id: UUID,
    asset_path: str,
    storage: ObjectStorage,
) -> FileAsset:
    file = require_existing_file(db, file_id=file_id)
    safe_asset_path = normalize_asset_path(asset_path)
    parse_job = require_latest_parse_job(db, file)
    parsed_result = get_parsed_result_location(parse_job)
    if parsed_result is None:
        raise ApiError(
            code="RESOURCE_NOT_FOUND",
            message="Parsed result asset was not found.",
            status_code=404,
        )

    result_bytes = storage.get_object(bucket=parsed_result["bucket"], key=parsed_result["key"])
    try:
        archive = zipfile.ZipFile(BytesIO(result_bytes))
    except zipfile.BadZipFile as exc:
        raise ApiError(
            code="VALIDATION_ERROR",
            message="Parsed result archive is invalid.",
            status_code=400,
        ) from exc

    archive_name = find_archive_asset_name(archive.namelist(), safe_asset_path)
    if archive_name is None:
        raise ApiError(
            code="RESOURCE_NOT_FOUND",
            message="Parsed result asset was not found.",
            status_code=404,
            details={"path": safe_asset_path},
        )
    return FileAsset(
        content=archive.read(archive_name),
        media_type=guess_media_type(archive_name),
    )


def require_existing_file(db: Session, *, file_id: UUID) -> File:
    file = db.get(File, file_id)
    if file is None or file.deleted_at is not None:
        raise ApiError(
            code="RESOURCE_NOT_FOUND",
            message="File was not found.",
            status_code=404,
        )
    return file


def require_latest_parse_job(db: Session, file: File) -> ParseJob:
    if file.latest_parse_job_id is None:
        raise ApiError(
            code="RESOURCE_NOT_FOUND",
            message="Parsed result asset was not found.",
            status_code=404,
        )
    parse_job = db.get(ParseJob, file.latest_parse_job_id)
    if parse_job is None:
        raise ApiError(
            code="RESOURCE_NOT_FOUND",
            message="Parsed result asset was not found.",
            status_code=404,
        )
    return parse_job


def normalize_asset_path(asset_path: str) -> str:
    stripped = asset_path.strip().replace("\\", "/").lstrip("/")
    normalized = posixpath.normpath(stripped)
    if not normalized or normalized == "." or normalized.startswith("../"):
        raise ApiError(
            code="VALIDATION_ERROR",
            message="Asset path is invalid.",
            status_code=422,
        )
    return normalized


def find_archive_asset_name(names: list[str], asset_path: str) -> str | None:
    normalized_names = {normalize_archive_name(name): name for name in names}
    if asset_path in normalized_names:
        return normalized_names[asset_path]
    suffix = f"/{asset_path}"
    for normalized_name, original_name in normalized_names.items():
        if normalized_name.endswith(suffix):
            return original_name
    return None


def normalize_archive_name(name: str) -> str:
    return posixpath.normpath(name.replace("\\", "/").lstrip("/"))


def guess_media_type(path: str) -> str:
    media_type, _encoding = mimetypes.guess_type(path)
    return media_type or "application/octet-stream"

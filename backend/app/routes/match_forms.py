from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette.datastructures import FormData, UploadFile

from app.ai.match.schemas import JobPosting
from app.core.config import settings
from app.core.uploads import (
    FORM_OVERHEAD_BYTES,
    BodyTooLargeError,
    MalformedFormError,
    read_multipart,
)
from app.integrations.doc_parse import read_capped, sniff_type
from app.integrations.errors import DocumentError, DocumentFailure, GitHubError
from app.integrations.github import parse_github_profile_url
from app.schemas.match import AnalysisInput
from app.services.match_failures import describe_failure
from app.services.match_service import CvUpload

MIN_CV_TEXT_CHARS = 50
MAX_CV_TEXT_CHARS = 40_000
# job, cv_text, github_url, consent, plus cv when a client sends an empty file as a plain field.
_ANALYSIS_FIELDS = 5
_RETRY_FIELDS = 3


def rejected(status_code: int, code: str) -> HTTPException:
    failure = describe_failure(code)
    return HTTPException(status_code, {"code": failure.code, "message": failure.message})


def _invalid(field: str, message: str) -> RequestValidationError:
    # Shape errors keep FastAPI's own 422 body, which the frontend already handles generically.
    return RequestValidationError([{"type": "value_error", "loc": ("body", field), "msg": message}])


async def _read_form(request: Request, *, max_fields: int) -> FormData:
    try:
        return await read_multipart(
            request,
            max_body_bytes=settings.max_upload_bytes + FORM_OVERHEAD_BYTES,
            max_files=1,
            max_fields=max_fields,
        )
    except BodyTooLargeError:
        raise rejected(status.HTTP_413_CONTENT_TOO_LARGE, "file_too_large") from None
    except MalformedFormError:
        raise _invalid("form", "expected a multipart form within the field limits") from None


def _text(form: FormData, name: str) -> str | None:
    value = form.get(name)
    if value is not None and not isinstance(value, str):
        raise _invalid(name, "must be a text field")
    return value.strip() or None if value is not None else None


def _chosen_file(form: FormData) -> UploadFile | None:
    upload = form.get("cv")
    if upload is None or upload == "":
        return None
    if not isinstance(upload, UploadFile):
        raise _invalid("cv", "must be a file")
    # A browser sends an empty, nameless part when the file input was left empty.
    return upload if upload.filename or upload.size else None


async def _cv(form: FormData) -> CvUpload | None:
    file = _chosen_file(form)
    text = _text(form, "cv_text")
    if file is not None and text is not None:
        raise rejected(status.HTTP_422_UNPROCESSABLE_CONTENT, "cv_and_cv_text")
    if text is not None:
        if not MIN_CV_TEXT_CHARS <= len(text) <= MAX_CV_TEXT_CHARS:
            raise _invalid("cv_text", "must be 50 to 40000 characters")
        return CvUpload(kind="text", data=text.encode())
    if file is None:
        return None
    try:
        data = await read_capped(file, settings.max_upload_bytes)
        sniff_type(data)
    except DocumentError as exc:
        if exc.failure is DocumentFailure.FILE_TOO_LARGE:
            raise rejected(status.HTTP_413_CONTENT_TOO_LARGE, "file_too_large") from None
        code = "unsafe_docx" if exc.failure is DocumentFailure.UNSAFE_DOCX else "unsupported_type"
        raise rejected(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, code) from None
    return CvUpload(kind="file", data=data)


async def analysis_form(request: Request) -> tuple[AnalysisInput, CvUpload | None]:
    form = await _read_form(request, max_fields=_ANALYSIS_FIELDS)
    if _text(form, "consent") != "true":
        raise rejected(status.HTTP_422_UNPROCESSABLE_CONTENT, "consent_required")
    try:
        posting = JobPosting.model_validate_json(_text(form, "job") or "")
    except ValidationError:
        raise rejected(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_job") from None
    github_url = _text(form, "github_url")
    cv = await _cv(form)
    if cv is None and github_url is None:
        raise rejected(status.HTTP_422_UNPROCESSABLE_CONTENT, "no_candidate_source")
    _github_url(form)
    return AnalysisInput(posting=posting, github_url=github_url, cv_provided=cv is not None), cv


def _github_url(form: FormData) -> str | None:
    github_url = _text(form, "github_url")
    if github_url is not None:
        try:
            parse_github_profile_url(github_url)
        except GitHubError:
            raise rejected(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_github_url") from None
    return github_url


async def retry_form(request: Request) -> tuple[CvUpload | None, str | None]:
    """The new CV for a CV retry, or an optional corrected URL for a GitHub retry."""
    content_type = request.headers.get("content-type", "").lower()
    if not content_type.startswith("multipart/form-data"):
        return None, None
    form = await _read_form(request, max_fields=_RETRY_FIELDS)
    return await _cv(form), _github_url(form)

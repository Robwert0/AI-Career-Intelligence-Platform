import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from redis.exceptions import RedisError

from app.ai.match.schemas import JobPosting
from app.core import policies
from app.core.job_store import JobRecord, JobStatus
from app.deps import get_current_user, get_match_service, rate_limit
from app.integrations.errors import FetchError
from app.models import User
from app.schemas.match import JobIntakeRequest, JobStatusResponse, JobSubmitted
from app.services.match_failures import describe_failure
from app.services.match_service import JobInProgressError, MatchService
from app.workers.queue import QueueUnavailableError

logger = logging.getLogger(__name__)

router = APIRouter()


def _unavailable() -> HTTPException:
    failure = describe_failure("unavailable")
    return HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        {"code": failure.code, "message": failure.message},
        headers={"Retry-After": "30"},
    )


def _not_found() -> HTTPException:
    failure = describe_failure("not_found")
    return HTTPException(
        status.HTTP_404_NOT_FOUND, {"code": failure.code, "message": failure.message}
    )


def _internal_error() -> HTTPException:
    failure = describe_failure("internal_error")
    return HTTPException(
        status.HTTP_500_INTERNAL_SERVER_ERROR, {"code": failure.code, "message": failure.message}
    )


def _stored_posting(record: JobRecord, raw: object) -> JobPosting | None:
    try:
        return None if raw is None else JobPosting.model_validate(raw)
    except ValidationError:
        # The pydantic error echoes input_value, which is posting text: log the type only.
        logger.warning("stored posting invalid job_id=%s error_type=ValidationError", record.id)
        return None


def _to_response(record: JobRecord) -> JobStatusResponse:
    result = record.result or {}
    source = result.get("source") or {}
    raw_posting = result.get("posting")
    posting = _stored_posting(record, raw_posting)
    if raw_posting is not None and posting is None:
        # A stored result that can never be shown ends the job; the poller needs a way out.
        record = record.model_copy(
            update={"status": JobStatus.FAILED, "error_code": "internal_error"}
        )
    try:
        return JobStatusResponse(
            job_id=record.id,
            status=record.status,
            stage=record.stage,
            error=describe_failure(record.error_code) if record.error_code else None,
            posting=posting,
            source_url=source.get("url"),
            input_truncated=bool(result.get("input_truncated", False)),
        )
    except ValidationError:
        logger.error("job response invalid job_id=%s error_type=ValidationError", record.id)
        raise _internal_error() from None


def _in_progress(job_id: str) -> JSONResponse:
    failure = describe_failure("job_in_progress")
    return JSONResponse(
        {"detail": {"code": failure.code, "message": failure.message}, "job_id": job_id},
        status_code=status.HTTP_409_CONFLICT,
    )


@router.post(
    "/jobs",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobSubmitted,
    dependencies=[Depends(rate_limit(policies.MATCH_JOB_USER))],
)
async def submit_job(
    payload: JobIntakeRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[MatchService, Depends(get_match_service)],
) -> JobSubmitted | JSONResponse:
    try:
        job_id = await service.submit_job(str(current_user.id), payload, now=time.time())
    except FetchError as exc:
        failure = describe_failure(exc.failure.value)
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"code": failure.code, "message": failure.message},
        ) from None
    except JobInProgressError as exc:
        return _in_progress(exc.job_id)
    except (QueueUnavailableError, RedisError) as exc:
        logger.warning("job submit unavailable error_type=%s", type(exc).__name__)
        raise _unavailable() from None
    return JobSubmitted(job_id=job_id)


@router.get(
    "/jobs/{job_id}",
    dependencies=[
        Depends(rate_limit(policies.MATCH_POLL_IP)),
        Depends(rate_limit(policies.MATCH_POLL_USER)),
    ],
)
async def get_job(
    job_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[MatchService, Depends(get_match_service)],
) -> JobStatusResponse:
    try:
        record = await service.get_job(str(current_user.id), job_id, now=time.time())
    except RedisError as exc:
        logger.warning("job poll unavailable error_type=%s", type(exc).__name__)
        raise _unavailable() from None
    if record is None:
        raise _not_found()
    return _to_response(record)

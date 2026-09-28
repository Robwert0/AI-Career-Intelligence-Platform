import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from redis.exceptions import RedisError

from app.ai.match.schemas import JobPosting
from app.core import policies
from app.core.job_store import JobRecord
from app.deps import get_current_user, get_match_service, rate_limit
from app.integrations.errors import FetchError
from app.models import User
from app.schemas.match import JobIntakeRequest, JobStatusResponse, JobSubmitted
from app.services.match_failures import describe_failure
from app.services.match_service import MatchService
from app.workers.queue import QueueUnavailableError

router = APIRouter()


def _unavailable() -> HTTPException:
    return HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE, "Service unavailable", headers={"Retry-After": "30"}
    )


def _to_response(record: JobRecord) -> JobStatusResponse:
    result = record.result or {}
    posting = result.get("posting")
    source = result.get("source") or {}
    return JobStatusResponse(
        job_id=record.id,
        status=record.status,
        stage=record.stage,
        error=describe_failure(record.error_code) if record.error_code else None,
        posting=JobPosting.model_validate(posting) if posting is not None else None,
        source_url=source.get("url"),
        input_truncated=bool(result.get("input_truncated", False)),
    )


@router.post(
    "/jobs",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit(policies.MATCH_JOB_USER))],
)
async def submit_job(
    payload: JobIntakeRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[MatchService, Depends(get_match_service)],
) -> JobSubmitted:
    try:
        job_id = await service.submit_job(str(current_user.id), payload, now=time.time())
    except FetchError as exc:
        failure = describe_failure(exc.failure.value)
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"code": failure.code, "message": failure.message},
        ) from None
    except QueueUnavailableError, RedisError:
        raise _unavailable() from None
    return JobSubmitted(job_id=job_id)


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[MatchService, Depends(get_match_service)],
) -> JobStatusResponse:
    try:
        record = await service.get_job(str(current_user.id), job_id, now=time.time())
    except RedisError:
        raise _unavailable() from None
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return _to_response(record)

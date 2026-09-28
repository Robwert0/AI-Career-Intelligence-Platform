import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from redis.exceptions import RedisError

from app.ai.match.schemas import JobPosting
from app.core import policies
from app.core.job_store import JobRecord, JobStatus
from app.deps import get_current_user, get_match_service, rate_limit
from app.integrations.errors import FetchError
from app.models import User
from app.routes.match_forms import analysis_form, rejected, retry_form
from app.schemas.match import (
    AnalysisStatusResponse,
    AnalysisSubmitted,
    DecisionOut,
    JobIntakeRequest,
    JobStatusResponse,
    JobSubmitted,
    MatchReport,
)
from app.services.match_failures import describe_failure
from app.services.match_service import (
    AnalysisInProgressError,
    AnalysisRunningError,
    AnalysisView,
    CvRequiredError,
    JobInProgressError,
    MatchService,
    NotAwaitingDecisionError,
    QueueFullError,
    RetryUrlNotAllowedError,
)
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


def _queue_full() -> HTTPException:
    failure = describe_failure("queue_full")
    return HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        {"code": failure.code, "message": failure.message},
        headers={"Retry-After": "60"},
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


def _stored_report(record: JobRecord) -> tuple[MatchReport | None, str | None]:
    """The stored report, or an error code when a done record has none that validates."""
    if record.status is not JobStatus.DONE:
        return None, None
    try:
        return MatchReport.model_validate((record.result or {}).get("report")), None
    except ValidationError as exc:
        # Type only: pydantic's message quotes the offending input, which can be CV text.
        logger.warning(
            "analysis report unreadable job_id=%s error_type=%s", record.id, type(exc).__name__
        )
        return None, "internal_error"


def _analysis_response(view: AnalysisView) -> AnalysisStatusResponse:
    record = view.record
    report, report_error = _stored_report(record)
    if report_error is not None:
        record = record.model_copy(update={"status": JobStatus.FAILED, "error_code": report_error})
    paused = record.status is JobStatus.NEEDS_DECISION
    return AnalysisStatusResponse(
        analysis_id=record.id,
        status=record.status,
        stage=record.stage,
        queue_position=view.queue_position,
        error=(
            describe_failure(record.error_code or "internal_error")
            if record.status is JobStatus.FAILED
            else None
        ),
        decision=(
            DecisionOut.model_validate(
                {
                    "failed_source": record.failed_source,
                    "error": describe_failure(record.error_code, retry_at=record.reset_at),
                }
            )
            if paused and record.failed_source and record.error_code
            else None
        ),
        report=report,
    )


def _analysis_in_progress(analysis_id: str) -> JSONResponse:
    failure = describe_failure("analysis_in_progress")
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "detail": {"code": failure.code, "message": failure.message},
            "analysis_id": analysis_id,
        },
    )


@router.post(
    "/analyses",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AnalysisSubmitted,
    dependencies=[Depends(rate_limit(policies.MATCH_ANALYSIS_USER))],
)
async def submit_analysis(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[MatchService, Depends(get_match_service)],
) -> AnalysisSubmitted | JSONResponse:
    # The body is read here, not by FastAPI, so auth and the rate limit run before any upload
    # is buffered and the size cap applies while reading (§6.2).
    analysis, cv = await analysis_form(request)
    try:
        analysis_id = await service.submit_analysis(
            str(current_user.id), analysis, cv, now=time.time()
        )
    except AnalysisInProgressError as exc:
        return _analysis_in_progress(exc.analysis_id)
    except QueueFullError:
        raise _queue_full() from None
    except QueueUnavailableError, RedisError:
        raise _unavailable() from None
    return AnalysisSubmitted(analysis_id=analysis_id)


@router.get(
    "/analyses/{analysis_id}",
    dependencies=[
        Depends(rate_limit(policies.MATCH_POLL_IP)),
        Depends(rate_limit(policies.MATCH_POLL_USER)),
    ],
)
async def get_analysis(
    analysis_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[MatchService, Depends(get_match_service)],
) -> AnalysisStatusResponse:
    try:
        view = await service.get_analysis(str(current_user.id), analysis_id, now=time.time())
    except RedisError:
        raise _unavailable() from None
    if view is None:
        raise rejected(status.HTTP_404_NOT_FOUND, "analysis_not_found")
    return _analysis_response(view)


@router.post(
    "/analyses/{analysis_id}/continue",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit(policies.MATCH_POLL_USER))],
)
async def continue_analysis(
    analysis_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[MatchService, Depends(get_match_service)],
) -> AnalysisSubmitted:
    try:
        resumed = await service.continue_analysis(
            str(current_user.id), analysis_id, now=time.time()
        )
    except NotAwaitingDecisionError:
        raise rejected(status.HTTP_409_CONFLICT, "not_awaiting_decision") from None
    except QueueUnavailableError, RedisError:
        raise _unavailable() from None
    if resumed is None:
        raise rejected(status.HTTP_404_NOT_FOUND, "analysis_not_found")
    return AnalysisSubmitted(analysis_id=resumed)


@router.post(
    "/analyses/{analysis_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit(policies.MATCH_ANALYSIS_USER))],
)
async def retry_analysis(
    analysis_id: str,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[MatchService, Depends(get_match_service)],
) -> AnalysisSubmitted:
    cv, github_url = await retry_form(request)
    try:
        resumed = await service.retry_analysis(
            str(current_user.id), analysis_id, cv, now=time.time(), github_url=github_url
        )
    except RetryUrlNotAllowedError:
        raise rejected(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_github_url") from None
    except NotAwaitingDecisionError:
        raise rejected(status.HTTP_409_CONFLICT, "not_awaiting_decision") from None
    except CvRequiredError:
        raise rejected(status.HTTP_422_UNPROCESSABLE_CONTENT, "no_candidate_source") from None
    except QueueUnavailableError, RedisError:
        raise _unavailable() from None
    if resumed is None:
        raise rejected(status.HTTP_404_NOT_FOUND, "analysis_not_found")
    return AnalysisSubmitted(analysis_id=resumed)


@router.post(
    "/analyses/{analysis_id}/discard",
    dependencies=[Depends(rate_limit(policies.MATCH_POLL_USER))],
)
async def discard_analysis(
    analysis_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[MatchService, Depends(get_match_service)],
) -> AnalysisSubmitted:
    try:
        discarded = await service.discard_analysis(
            str(current_user.id), analysis_id, now=time.time()
        )
    except AnalysisRunningError:
        raise rejected(status.HTTP_409_CONFLICT, "analysis_running") from None
    except RedisError:
        raise _unavailable() from None
    if discarded is None:
        raise rejected(status.HTTP_404_NOT_FOUND, "analysis_not_found")
    return AnalysisSubmitted(analysis_id=discarded)

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.ai.generation import GeneratorUnavailableError
from app.ai.rag import RagPipeline
from app.core import policies
from app.core.config import settings
from app.deps import get_current_user, get_rag_pipeline, rate_limit
from app.models import User
from app.schemas import ChatRequest, ChatResponse, Source

router = APIRouter()


@router.post(
    "",
    status_code=status.HTTP_200_OK,
    dependencies=[
        Depends(rate_limit(policies.CHAT_IP)),
        Depends(rate_limit(policies.CHAT_USER)),
    ],
)
async def chat(
    payload: ChatRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    pipeline: Annotated[RagPipeline, Depends(get_rag_pipeline)],
) -> ChatResponse:
    try:
        answer = await pipeline.answer(payload.message)
    except GeneratorUnavailableError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Service unavailable",
            headers={"Retry-After": str(settings.chat_timeout_seconds)},
        ) from None

    return ChatResponse(
        answer=answer.text,
        refused=answer.refused,
        sources=[Source(section=chunk.section, content=chunk.content) for chunk in answer.sources],
    )

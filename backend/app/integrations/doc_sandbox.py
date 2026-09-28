import asyncio
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from app.integrations.doc_parse import DocumentKind, ParsedDocument
from app.integrations.errors import DocumentError, DocumentFailure

logger = logging.getLogger(__name__)

PARSE_TIMEOUT_SECONDS = 30.0
PARSE_MEMORY_BYTES = 512 * 1024 * 1024
_BACKEND_ROOT = Path(__file__).resolve().parents[2]


class _ChildReply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: DocumentFailure | None = None
    kind: DocumentKind | None = None
    text: str | None = None
    pages: int | None = None
    truncated: bool = False


def _child_command(memory_bytes: int) -> list[str]:
    # -E ignores PYTHON* variables and -s the user site, so the child imports only this code.
    return [sys.executable, "-E", "-s", "-m", "app.integrations.doc_child", str(memory_bytes)]


async def parse_isolated(
    data: bytes,
    *,
    timeout: float = PARSE_TIMEOUT_SECONDS,
    memory_bytes: int = PARSE_MEMORY_BYTES,
    command: Sequence[str] | None = None,
) -> ParsedDocument:
    """Parses in a killable child process: a hostile file can hang or bloat it, not the worker."""
    process = await asyncio.create_subprocess_exec(
        *(command or _child_command(memory_bytes)),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        cwd=_BACKEND_ROOT,
        env={"LC_ALL": "C.UTF-8"},
    )
    try:
        async with asyncio.timeout(timeout):
            output, _ = await process.communicate(data)
    except TimeoutError:
        logger.warning("document parse stopped reason=timeout bytes=%d", len(data))
        raise DocumentError(DocumentFailure.UNREADABLE_DOCUMENT) from None
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()

    if process.returncode != 0:
        logger.warning(
            "document parse crashed exit_code=%s bytes=%d", process.returncode, len(data)
        )
        raise DocumentError(DocumentFailure.UNREADABLE_DOCUMENT)
    try:
        reply = _ChildReply.model_validate_json(output)
    except ValidationError:
        raise DocumentError(DocumentFailure.UNREADABLE_DOCUMENT) from None
    if reply.error is not None:
        raise DocumentError(reply.error)
    if reply.kind is None or reply.text is None:
        raise DocumentError(DocumentFailure.UNREADABLE_DOCUMENT)
    return ParsedDocument(
        kind=reply.kind, text=reply.text, pages=reply.pages, truncated=reply.truncated
    )

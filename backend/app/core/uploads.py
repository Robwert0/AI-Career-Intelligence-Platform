from collections.abc import AsyncGenerator

from python_multipart.exceptions import FormParserError
from starlette.datastructures import FormData
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.requests import Request

MAX_FIELD_BYTES = 256 * 1024
FORM_OVERHEAD_BYTES = 1024 * 1024
_MULTIPART = "multipart/form-data"


class BodyTooLargeError(Exception):
    """The request body is larger than the route accepts."""


class MalformedFormError(Exception):
    """The body is not a well-formed multipart form within the field limits."""


class _InMemoryParser(MultiPartParser):
    # Starlette rolls file parts over 1 MiB into a temp file on disk; D6 forbids any disk.
    # The body is capped far below this, so a file part never leaves memory.
    spool_max_size = 64 * 1024 * 1024


async def read_body(request: Request, *, limit: int) -> bytes:
    declared = request.headers.get("content-length")
    if declared is not None:
        if not declared.isdigit():
            raise MalformedFormError("content-length")
        # Refuse before reading a byte: a 413 must never cost buffering the upload.
        if int(declared) > limit:
            raise BodyTooLargeError
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > limit:
            raise BodyTooLargeError
    return bytes(body)


async def _once(body: bytes) -> AsyncGenerator[bytes]:
    yield body


async def read_multipart(
    request: Request, *, max_body_bytes: int, max_files: int, max_fields: int
) -> FormData:
    if max_body_bytes >= _InMemoryParser.spool_max_size:
        raise ValueError("the body cap must stay below the in-memory spool size")
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != _MULTIPART:
        raise MalformedFormError("content-type")
    body = await read_body(request, limit=max_body_bytes)
    parser = _InMemoryParser(
        request.headers,
        _once(body),
        max_files=max_files,
        max_fields=max_fields,
        max_part_size=MAX_FIELD_BYTES,
    )
    try:
        return await parser.parse()
    # python-multipart raises its own errors for a broken stream; Starlette only wraps some.
    except MultiPartException, FormParserError:
        raise MalformedFormError("multipart") from None

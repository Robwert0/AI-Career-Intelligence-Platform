import os
import tempfile
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from starlette.applications import Starlette
from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import Message

from app.core.uploads import (
    MAX_FIELD_BYTES,
    BodyTooLargeError,
    MalformedFormError,
    read_body,
    read_multipart,
)

LIMIT = 6 * 1024 * 1024
FILE = os.urandom(5 * 1024 * 1024 - 7)


async def _echo(request: Request) -> JSONResponse:
    try:
        form = await read_multipart(request, max_body_bytes=LIMIT, max_files=1, max_fields=4)
    except BodyTooLargeError:
        return JSONResponse({"error": "too_large"}, status_code=413)
    except MalformedFormError:
        return JSONResponse({"error": "malformed"}, status_code=422)
    upload = form.get("cv")
    data = await upload.read() if isinstance(upload, UploadFile) else b""
    return JSONResponse(
        {"fields": sorted(key for key in form if key != "cv"), "same": data == FILE}
    )


async def _stock(request: Request) -> JSONResponse:
    await request.form()
    return JSONResponse({})


APP = Starlette(
    routes=[Route("/echo", _echo, methods=["POST"]), Route("/stock", _stock, methods=["POST"])]
)


@pytest.fixture
def no_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a temp file was created on disk")

    for name in ("TemporaryFile", "NamedTemporaryFile", "mkstemp", "mkdtemp"):
        monkeypatch.setattr(tempfile, name, refuse)


async def post(path: str, **kwargs: Any) -> httpx.Response:
    transport = httpx.ASGITransport(app=APP)
    async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
        return await client.post(path, **kwargs)


async def test_the_guard_catches_starlettes_default_spooling(no_disk: None) -> None:
    # Control: without this proof the no-disk test below could pass vacuously.
    with pytest.raises(AssertionError, match="on disk"):
        await post("/stock", files={"cv": ("cv.pdf", FILE, "application/pdf")})


async def test_a_5_mb_upload_is_parsed_without_touching_disk(no_disk: None) -> None:
    response = await post(
        "/echo",
        files={"cv": ("cv.pdf", FILE, "application/pdf")},
        data={"job": "{}", "consent": "true"},
    )

    assert response.status_code == 200
    assert response.json() == {"fields": ["consent", "job"], "same": True}


async def test_a_body_over_the_cap_is_refused(no_disk: None) -> None:
    response = await post("/echo", files={"cv": ("cv.pdf", os.urandom(LIMIT), "application/pdf")})

    assert response.status_code == 413


async def test_a_declared_length_over_the_cap_is_refused_before_any_read() -> None:
    scope: dict[str, Any] = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [
            (b"content-type", b"multipart/form-data; boundary=x"),
            (b"content-length", str(LIMIT + 1).encode()),
        ],
    }

    async def receive() -> Message:
        raise AssertionError("the body was read")

    with pytest.raises(BodyTooLargeError):
        await read_body(Request(scope, receive), limit=LIMIT)


async def test_a_chunked_body_without_a_length_is_capped_while_streaming() -> None:
    async def chunks() -> AsyncIterator[bytes]:
        for _ in range(8):
            yield b"x" * (1024 * 1024)

    response = await post(
        "/echo",
        content=chunks(),
        headers={"content-type": "multipart/form-data; boundary=x"},
    )

    assert response.status_code == 413


@pytest.mark.parametrize(
    "kwargs",
    [
        {"json": {"job": "{}"}},
        {"content": b"--x\r\n", "headers": {"content-type": "multipart/form-data"}},
        {"data": {"a": "1", "b": "2", "c": "3", "d": "4", "e": "5"}, "files": {"f": ("f", b"1")}},
        {"data": {"job": "x" * (MAX_FIELD_BYTES + 1)}, "files": {"f": ("f", b"1")}},
        {"files": [("cv", ("a.pdf", b"1")), ("cv2", ("b.pdf", b"2"))]},
        {"content": b"garbage", "headers": {"content-type": "multipart/form-data; boundary=x"}},
        {
            "content": b"--x\r\nbad header line\r\n\r\nv\r\n--x--\r\n",
            "headers": {"content-type": "multipart/form-data; boundary=x"},
        },
    ],
    ids=[
        "not-multipart",
        "no-boundary",
        "too-many-fields",
        "field-too-big",
        "two-files",
        "garbage",
        "bad-part-header",
    ],
)
async def test_malformed_forms_are_rejected(kwargs: dict[str, Any]) -> None:
    response = await post("/echo", **kwargs)

    assert response.status_code == 422

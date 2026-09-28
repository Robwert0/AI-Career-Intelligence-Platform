import asyncio
import multiprocessing
import sys
import time
from typing import Any

import pytest
from documents import CV_LINE, cv_docx, make_pdf, text_page

from app.integrations.doc_sandbox import parse_isolated
from app.integrations.errors import DocumentError, DocumentFailure


async def failure_of(data: bytes, **kwargs: Any) -> DocumentFailure:
    with pytest.raises(DocumentError) as caught:
        await parse_isolated(data, **kwargs)
    return caught.value.failure


async def test_a_pdf_parses_in_the_child() -> None:
    parsed = await parse_isolated(make_pdf([text_page(), text_page()]))

    assert (parsed.kind, parsed.pages) == ("pdf", 2)
    assert CV_LINE in parsed.text


async def test_a_docx_parses_in_the_child() -> None:
    parsed = await parse_isolated(cv_docx())

    assert parsed.kind == "docx"
    assert "Go | Expert" in parsed.text


async def test_the_childs_own_failure_code_comes_back() -> None:
    assert await failure_of(make_pdf(["", ""])) is DocumentFailure.SCANNED_PDF_SUSPECTED
    assert await failure_of(b"MZ\x90\x00") is DocumentFailure.UNSUPPORTED_TYPE


async def test_a_hanging_parse_is_killed_at_the_timeout() -> None:
    started = time.monotonic()

    failure = await failure_of(
        b"", timeout=1.0, command=[sys.executable, "-c", "import time; time.sleep(60)"]
    )

    assert failure is DocumentFailure.UNREADABLE_DOCUMENT
    assert time.monotonic() - started < 5


async def test_the_child_runs_under_its_memory_limit() -> None:
    # 32 MiB cannot even hold the PDF parser's imports, so the child must die, not parse.
    failure = await failure_of(make_pdf([text_page()]), memory_bytes=32 * 1024 * 1024)

    assert failure is DocumentFailure.UNREADABLE_DOCUMENT


async def test_a_crashing_child_is_unreadable() -> None:
    failure = await failure_of(b"", command=[sys.executable, "-c", "raise SystemExit(3)"])

    assert failure is DocumentFailure.UNREADABLE_DOCUMENT


async def test_garbage_on_stdout_is_unreadable() -> None:
    failure = await failure_of(b"", command=[sys.executable, "-c", "print('not json')"])

    assert failure is DocumentFailure.UNREADABLE_DOCUMENT


async def test_the_child_never_writes_document_text_to_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("DEBUG"):
        await failure_of(
            CV_LINE.encode(), command=[sys.executable, "-c", "import sys; sys.exit(1)"]
        )

    assert "crashed" in caplog.text
    assert "Acme" not in caplog.text


def _parse_in_daemon(queue: multiprocessing.Queue[str]) -> None:
    parsed = asyncio.run(parse_isolated(make_pdf([text_page()])))
    queue.put(parsed.kind)


def test_parsing_works_from_a_daemonic_process_like_a_celery_child() -> None:
    # Celery's prefork children are daemonic, and daemonic processes may not use
    # multiprocessing children; a plain subprocess must still work there.
    context = multiprocessing.get_context("fork")
    queue: multiprocessing.Queue[str] = context.Queue()
    child = context.Process(target=_parse_in_daemon, args=(queue,), daemon=True)
    child.start()
    child.join(timeout=30)

    assert child.exitcode == 0
    assert queue.get(timeout=1) == "pdf"

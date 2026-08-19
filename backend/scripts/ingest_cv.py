import argparse
import asyncio
import hashlib
import sys
import uuid
from pathlib import Path

from app.ai.embeddings import BgeEmbedder
from app.core.db import SessionLocal
from app.repositories import ChunkRepository
from app.services.cv_parser import UnreadablePdfError
from app.services.ingestion_service import EmptyDocumentError, IngestionService

CV_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "cv.ai-career-intelligence")


def document_id_for(pdf_bytes: bytes) -> uuid.UUID:
    return uuid.uuid5(CV_NAMESPACE, hashlib.sha256(pdf_bytes).hexdigest())


async def ingest(pdf_bytes: bytes, document_id: uuid.UUID) -> int:
    async with SessionLocal() as session:
        service = IngestionService(ChunkRepository(session), BgeEmbedder())
        written = await service.ingest(pdf_bytes, document_id)
        # Nothing else commits: get_db owns the transaction inside FastAPI, not here.
        await session.commit()
    return written


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingest a CV PDF into the chunks table.",
        epilog=(
            "Run from the backend/ directory with DATABASE_URL set. Re-ingesting the same "
            "file replaces that document's chunks rather than duplicating them. "
            "Exit codes: 0 ok, 1 no extractable text, 2 bad path, 3 unreadable PDF."
        ),
    )
    parser.add_argument("pdf", type=Path, help="path to the CV PDF")
    pdf_path: Path = parser.parse_args().pdf

    if not pdf_path.is_file():
        print(f"not a file: {pdf_path}", file=sys.stderr)
        return 2

    pdf_bytes = pdf_path.read_bytes()
    document_id = document_id_for(pdf_bytes)
    try:
        written = asyncio.run(ingest(pdf_bytes, document_id))
    except EmptyDocumentError:
        print(f"no extractable text in {pdf_path}", file=sys.stderr)
        return 1
    except UnreadablePdfError as exc:
        print(f"could not read {pdf_path} as a PDF: {exc}", file=sys.stderr)
        return 3

    print(f"{pdf_path.name}: {written} chunks -> document {document_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

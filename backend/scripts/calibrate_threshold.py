import argparse
import asyncio
import statistics

from app.ai.embeddings import BgeEmbedder
from app.ai.retriever import Retriever
from app.core.config import settings
from app.core.db import SessionLocal
from app.repositories import ChunkRepository

SHOULD_ANSWER = [
    "What is his current role?",
    "Which message broker has he worked with?",
    "What databases has he used in production?",
    "Where did he do his bachelor's degree?",
    "What is he studying now?",
    "Has he done any internships?",
    "What did he build with OpenCV?",
    "Does he have experience with FastAPI?",
    "What does he use for monitoring and alerting?",
    "What is the Jarvis project?",
]

SHOULD_REFUSE = [
    "What did he do at Google?",
    "How many years of Rust does he have?",
    "What Kubernetes experience does he have?",
    "What did he study at Oxford?",
    "Which AWS certifications does he hold?",
    "How many engineers has he managed?",
    "What papers has he published?",
    "What is his salary expectation?",
    "What is his GPA?",
    "Who is the president of France?",
]


async def measure(questions: list[str]) -> list[tuple[str, float, int]]:
    async with SessionLocal() as session:
        retriever = Retriever(ChunkRepository(session), BgeEmbedder())
        rows = []
        for question in questions:
            result = await retriever.retrieve(
                question,
                document_id=settings.cv_document_id,
                limit=settings.retrieval_limit,
            )
            rows.append((question, result.best_similarity, result.text_hit_count))
        return rows


async def run() -> int:
    answerable = await measure(SHOULD_ANSWER)
    refusable = await measure(SHOULD_REFUSE)

    for label, rows in (("ANSWER", answerable), ("REFUSE", refusable)):
        for question, similarity, hits in sorted(rows, key=lambda row: row[1]):
            print(f"{label}\t{similarity:.4f}\tfts={hits}\t{question}")

    lowest_answer = min(similarity for _, similarity, _ in answerable)
    highest_refuse = max(similarity for _, similarity, _ in refusable)
    silent_refusals = [row for row in refusable if row[2] == 0]

    print()
    print(f"document                {settings.cv_document_id}")
    print(f"lowest  ANSWER          {lowest_answer:.4f}")
    print(f"highest REFUSE          {highest_refuse:.4f}")
    print(f"median  ANSWER          {statistics.median(s for _, s, _ in answerable):.4f}")
    print(f"median  REFUSE          {statistics.median(s for _, s, _ in refusable):.4f}")
    print(f"REFUSE rows with no fts {len(silent_refusals)}/{len(refusable)}")

    if lowest_answer <= highest_refuse:
        print()
        print("NO CLEAN SEPARATION: the sets overlap, so no threshold divides them.")
        print("Record this as a finding. The prompt-level refusal instruction is carrying")
        print("the weight; do not tune the number until the sets actually split.")
        return 1

    suggested = (lowest_answer + highest_refuse) / 2
    print()
    print(f"suggested threshold     {suggested:.4f}")
    return 0


def main() -> int:
    argparse.ArgumentParser(
        description="Measure retrieval similarity for should-answer and should-refuse questions.",
        epilog=(
            "Run from backend/ with DATABASE_URL and CV_DOCUMENT_ID set. Edit the two question "
            "lists to match the ingested CV before trusting the output."
        ),
    ).parse_args()
    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())

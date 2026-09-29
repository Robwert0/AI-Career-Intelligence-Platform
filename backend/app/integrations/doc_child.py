import json
import resource
import sys


def main() -> int:
    # The limit must be set before the parser is imported, so it covers everything after it.
    limit = int(sys.argv[1])
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))

    try:
        from app.integrations.doc_parse import parse_document
        from app.integrations.errors import DocumentError
    except MemoryError:
        # Under a tight enough limit, even the parser's own imports don't fit: report that
        # cleanly instead of letting it crash the interpreter with no reply at all.
        sys.stdout.write(json.dumps({"error_type": "MemoryError"}))
        return 0

    try:
        parsed = parse_document(sys.stdin.buffer.read())
    except DocumentError as exc:
        reply: dict[str, object] = {"error": exc.failure.value}
    except Exception as exc:
        # Never the exception's own message: pdfminer and friends sometimes embed a snippet
        # of the document they choked on. The type name alone is enough to debug by.
        reply = {"error_type": type(exc).__name__}
    else:
        reply = {
            "kind": parsed.kind,
            "text": parsed.text,
            "pages": parsed.pages,
            "truncated": parsed.truncated,
        }
    sys.stdout.write(json.dumps(reply))
    return 0


if __name__ == "__main__":
    sys.exit(main())

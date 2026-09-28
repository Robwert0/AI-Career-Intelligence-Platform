import json
import resource
import sys


def main() -> int:
    # The limit must be set before the parser is imported, so it covers everything after it.
    limit = int(sys.argv[1])
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))

    from app.integrations.doc_parse import parse_document
    from app.integrations.errors import DocumentError

    try:
        parsed = parse_document(sys.stdin.buffer.read())
    except DocumentError as exc:
        reply: dict[str, object] = {"error": exc.failure.value}
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

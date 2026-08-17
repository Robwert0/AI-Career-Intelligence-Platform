# testdata/ — local only, never committed

Drop real CVs here to validate the PDF parser against genuine generator output. Everything in
this directory except this file is gitignored.

**Why not committed:** real CVs carry third-party personal data — names, phone numbers,
employment history. "Anonymised" public datasets frequently are not, and git history is
permanent. This repository is public.

Committed test fixtures are synthetic and live in `backend/tests/fixtures/`.

## What's worth putting here

The parser breaks on the *generator*, not the content — specifically the `"Bold" in fontname`
check. Exporting the same CV from several tools gives more signal than many CVs from one:

| tool | font names it produces |
|------|------------------------|
| Word | `Arial-BoldMT`, `Calibri-Bold` |
| Google Docs | embedded subsets, e.g. `ABCDEF+Arial-Bold` |
| LaTeX / Overleaf | `NimbusSanL-Bold`, sometimes just `F1`, `F2` |
| Canva | often outlines text — **no text layer at all**, `page.chars` is empty |

Bulk sources if volume is wanted: the Kaggle Resume Dataset (~2400 PDFs, single generator so
limited template diversity), and `Mehyaar/Annotated_NER_PDF_Resumes` on HuggingFace.

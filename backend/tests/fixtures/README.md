# Synthetic CV fixtures

Fabricated CVs, safe to commit. Each targets a specific parser failure mode found by testing
against real output — they exist to fail, not to pass.

| file | what it tests | current outcome |
|------|---------------|-----------------|
| `sample_cv.md` | markdown path, no PDF involved | chunker input |
| `a_titlecase.pdf` | Title Case headings (`Work Experience`), clear size margin | passes **only** with character-weighted body size — line-weighted ties 3 headings against 3 body lines and picks the heading size as "body" |
| `b_narrowmargin.pdf` | 10pt headings over 9.5pt body (ratio 1.053) | **fails** any size-margin rule that also works on a CV whose entry titles are 9.5pt over 9pt body (ratio 1.056). No single margin satisfies both — this is why word matching is needed |
| `c_twocolumn.pdf` | two-column layout | **fails**: grouping by vertical position merges columns, so `EXPERIENCE` + `SKILLS` become one line and body text interleaves |
| `d_nobold.pdf` | ALL-CAPS headings that are larger but **not bold** | **fails**: finds zero headings, since bold is required |

| `f_oversized.md` | the chunker's FIT step — no PDF involved | `experience` is 657 tokens over 14 paragraphs (none above 73), so greedy **paragraph packing** must split it. `projects` is 605 tokens in a **single 604-token paragraph**, so paragraph packing cannot help and the **sentence-level fallback** must run. The other four sections fit in one chunk each, which proves FIT fires only when needed. |

Every other fixture has all sections under the 510-token budget, so without `f_oversized.md`
the entire FIT step would be unreachable code that no test could distinguish from correct.

`c_` and `d_` produce *no usable headings*. That is a legitimate outcome, not a bug to fix in the
parser — it is why the chunker must fall back to splitting on token budget. A CV that parses into
one heading-less blob still has to become usable chunks.

Real CVs for local validation go in the gitignored `testdata/` at the repo root.

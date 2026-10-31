# Essay report style refinement

The first BA3073 application-generated report preserved deployment evidence, but
its captions and narrative repeated evidence limitations and discussed the report
inputs as an external reviewer. This refinement improves the writing instructions
in `backend/pipelines/essay_html.py`.

## Change

- General essay guidance requests precise academic prose, coherent paragraphs,
  consistent terminology and readable print pagination.
- Conditional BA3073 guidance requests a student technical-report voice that
  connects purpose, configuration/action, observed result and interpretation.
- Material limitations remain in the completion table and test discussion;
  captions add a limitation when a specific misinterpretation needs preventing.
- Writing constraints are not copied into the report as assistant/editor notes.
  Verified later records take precedence over earlier pending snapshots.

The self-contained HTML contract, source preservation on conversion failure,
evidence integrity, secret exclusion, original test outcomes, conditional Task 3
completion requirements and 20-page total limit remain intact. The deterministic
author-credit insertion and PDF author metadata code were not changed. No API,
storage, authentication, provider-default or artifact-access contract changed.

## Verification

- `uv run --isolated --no-project --with-requirements backend/requirements-dev.txt python -m pytest backend/tests/test_essay_pipeline.py -q`:
  **3 passed in 0.15s**. Model and PDF conversion are mocked in these tests.
- Python AST parsing and `git diff --check`: passed.
- Independent diff review: passed; assignment scope and evidence safeguards
  remain intact.
- Local derivative image activated through the existing Compose service with
  `--no-build`; source SHA256 matches between host and container and `/health`
  returns HTTP 200. Runtime evidence is kept outside the public source repository.

A comparative real application generation succeeded with the existing model
profile. Its five-page body was combined with eight original screenshot pages
into a 13-page report. Independent content and visual review found clearer
technical-report prose and fewer repeated caveats while retaining the original
failed test and incomplete domain status. The automatic author credit remained
present. The preserved original body text was not rewritten; a print-only CSS
adjustment removed duplicate reference-list numbering.

Prompt instructions encourage a writing style but do not guarantee factual
accuracy or rendered page count; each final report still requires its own
evidence and visual review.

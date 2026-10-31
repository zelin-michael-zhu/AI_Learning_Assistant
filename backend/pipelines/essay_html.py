from __future__ import annotations

import json
from typing import Any, Callable

from backend.artifacts.filesystem import ArtifactRun
from backend.pipelines.authorship import add_author_credit
from backend.pipelines.common import (
    PipelineError,
    PipelineResult,
    extract_fenced_or_raw,
    format_citations,
    format_log,
)
from backend.pipelines.html_to_pdf import (
    A4_PAGE,
    ConvertError,
    HtmlToPdfConverter,
)
from backend.providers.base import (
    ModelProviderError,
    TextGenerationProvider,
    TextGenerationRequest,
)
from backend.timing import RunTimingRecorder, measure_stage


def run_essay_html_pipeline(
    *,
    artifact_run: ArtifactRun,
    model_profile: dict[str, Any],
    model_provider: TextGenerationProvider,
    pdf_converter: HtmlToPdfConverter,
    task_text: str,
    context_bundle: str,
    output_preference: str | None,
    options: dict[str, Any] | None,
    search: dict[str, Any],
    max_output_tokens: int,
    emit_event: Callable[[str, str], None] | None = None,
    timing: RunTimingRecorder | None = None,
) -> PipelineResult:
    log_lines = [
        "Pipeline: essay_html",
        f"Output preference: {output_preference or 'pdf'}",
        "Stage: generate_source",
    ]
    system_prompt, user_prompt = build_essay_html_prompt(
        task_text=task_text,
        context_bundle=context_bundle,
        options=options or {},
        search=search,
    )
    if emit_event:
        emit_event("generate_source", "Generating essay HTML source")

    try:
        with measure_stage(timing, "provider_generation"):
            raw_output = model_provider.generate_text(
                TextGenerationRequest(
                    profile=model_profile,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_output_tokens=max_output_tokens,
                    temperature=0.2,
                )
            )
    except ModelProviderError as exc:
        raise PipelineError(
            exc.code,
            exc.message,
            stage="generate_source",
            log_lines=log_lines,
        ) from exc
    except Exception as exc:
        raise PipelineError(
            "provider_unavailable",
            "The model provider request failed.",
            stage="generate_source",
            log_lines=log_lines,
        ) from exc

    source = extract_fenced_or_raw(raw_output, accepted_languages={"html", "htm"})
    source = add_author_credit(source.strip()) + "\n"
    html_path = artifact_run.write_output(
        "main.html",
        source,
        kind="source",
        media_type="text/html",
    )
    log_lines.extend(["Output: output/main.html", "Stage: convert_pdf"])
    if emit_event:
        emit_event("convert_pdf", "Converting essay HTML to PDF")

    pdf_path = artifact_run.run_dir / "output" / "main.pdf"
    try:
        with measure_stage(timing, "convert_pdf"):
            convert_result = pdf_converter.convert(
                html_path=html_path,
                pdf_path=pdf_path,
                page_config=A4_PAGE,
            )
    except ConvertError as exc:
        artifact_run.write_log("convert.log", exc.log_text)
        raise PipelineError(
            "convert_failed",
            exc.message,
            stage="convert_pdf",
            log_lines=log_lines,
        ) from exc
    except Exception as exc:
        artifact_run.write_log(
            "convert.log",
            "HTML-to-PDF converter raised an unexpected error.\n",
        )
        raise PipelineError(
            "convert_failed",
            "HTML-to-PDF conversion failed.",
            stage="convert_pdf",
            log_lines=log_lines,
        ) from exc

    artifact_run.write_log("convert.log", convert_result.log_text)
    artifact_run.write_output(
        "main.pdf",
        convert_result.pdf_path.read_bytes(),
        kind="pdf",
        media_type="application/pdf",
    )
    log_lines.extend(["Convert: pdf_ok", "Output: output/main.pdf"])
    return PipelineResult(log_text=format_log(log_lines))


def build_essay_html_prompt(
    *,
    task_text: str,
    context_bundle: str,
    options: dict[str, Any],
    search: dict[str, Any],
) -> tuple[str, str]:
    system_prompt = (
        "You are an expert teaching assistant writing complete academic essay and "
        "report deliverables as self-contained HTML documents. Return only the "
        "requested HTML source, with no surrounding explanation."
    )
    output_instruction = (
        "Return one complete self-contained HTML document. It must start with "
        "<!doctype html> and include <html>, <head>, and <body>. Include all CSS "
        "inside a <style> element: use a readable serif academic print layout, "
        "clear heading hierarchy, careful paragraph spacing, and CSS "
        "@page { size: A4; margin: 20mm; }. Do not use external stylesheet links, "
        "remote images, or remote HTTP(S) assets. If mathematical notation is "
        "needed, include inline KaTeX-compatible markup and any needed minimal "
        "KaTeX styling inline in the document; do not fetch KaTeX from a CDN at "
        "render time. Use inline SVG or CSS for diagrams. Cite any provided web "
        "sources in a References section using ordinary HTML. Do not wrap the "
        "answer in Markdown fences."
        "\n\nWriting quality: produce a finished academic document in the "
        "requested language and genre. Use precise, restrained language, "
        "concrete verbs, consistent technical terms, and paragraphs that develop "
        "one main point with evidence and explanation. Prefer clear reasoning "
        "over ornate vocabulary, inflated claims, generic introductions, or "
        "repetitive summaries. Use numbered sections, informative table/figure "
        "captions, and consistent citations where appropriate. Keep table "
        "captions with their tables, repeat table headers across page breaks, "
        "and avoid isolated headings, clipped text, or unreadably small type."
        "\n\nConditional assignment guidance: apply the following only when the "
        "Assignment Task explicitly requests the BA3073 take-home deployment "
        "report, 'From AI Agent to Cloud Service'. Do not apply this structure "
        "to unrelated essays, or infer that it applies from a course name in "
        "a byline or reference alone. Follow the user's requested language."
        "\n\nReport structure: begin with a title, a concise overview, and a "
        "Task 1/2/3 completion table distinguishing completed, partially "
        "completed, not performed, and unverified work. Explain the system "
        "architecture and request flow: browser /ui/, FastAPI, model provider, "
        "SQLite metadata, artifact files, and HTML-to-PDF conversion. Describe "
        "the actual local Docker build and checks; the ECS-compatible Linux "
        "image build (including linux/amd64 when supported by the evidence), "
        "local image test, ACR push, ECS pull, Compose startup, published ports, "
        "persistent data/workspace volumes, secret handling, and security-group "
        "source restrictions. Distinguish an image, a running container, and "
        "persistent host data. Explain the revised report-generation "
        "instructions and their purpose using the supplied source changes. "
        "Then cover domain deployment, test results and their scope, limitations, "
        "security/cost/reliability improvements, and a conclusion with references."
        "\n\nTechnical-report voice: write as the student author presenting "
        "the deployment, rather than as an assistant reviewing the student's "
        "materials. For each major step, connect its purpose, the relevant "
        "configuration or action, the observed result, and its technical "
        "implication. Use past tense for performed work and clearly conditional "
        "or future language for proposals. Include short command/configuration "
        "examples only when they help reproduction or explanation. Concentrate "
        "completion limits in the status table and test/limitations discussion; "
        "elsewhere use brief cross-references instead of repeating every caveat. "
        "Treat the evidence rules below as writing constraints, not prose to "
        "copy into the report. Avoid assistant commentary, instructions to an "
        "editor, and repeated discussion of prompt inputs or model access to "
        "image bytes. Explain instruction changes and verified application "
        "generation in one concise implementation subsection when relevant."
        "\n\nDomain workflow: explain, in order, control of a domain/subdomain "
        "and any applicable ICP filing/access prerequisites; DNS A resolution "
        "to the ECS IPv4; inbound TCP 80/443; a dedicated Nginx site proxying "
        "to 127.0.0.1:14242; configuration validation and reload; a working "
        "domain HTTP check; Certbot certificate issuance and verified HTTPS; "
        "reverse-proxy access control independent of BNBU application login, "
        "with allowed and denied access checks; then returning the application "
        "port binding to loopback and removing public 14242 access without "
        "reopening it through another broad security-group rule. Explain why "
        "each step is needed. Label unexecuted steps as a proposed procedure, "
        "separate from performed work. If filing/access is blocked or deferred, "
        "state that limitation; DNS resolution and a valid Nginx configuration "
        "alone do not establish application reachability, HTTPS, or successful "
        "access control. Do not call Task 3 complete without evidence of its "
        "working HTTPS domain and independent access-control check."
        "\n\nEvidence rules: base deployment facts only on the task input and "
        "supplied/uploaded evidence. Identify each important result by its "
        "evidence filename, execution location, timestamp, tested URL/endpoint, "
        "and observed status when available; say when these details are absent. "
        "Keep commands that were executed separate from illustrative commands. "
        "Preserve original PASS/FAIL results and HTTP/curl codes. If an ECS "
        "self-public-IP check reports FAIL/HTTP 000 while a Mac public-IP check "
        "and ECS loopback check report HTTP 200, present all results together "
        "as different test paths, including any separate /health result. "
        "Do not replace the failed ECS result with the external success, or "
        "assert hairpin NAT limitations or the security group's observed "
        "source address without direct evidence; a local route alone does not "
        "prove either cause. Separate observations, hypotheses, and next checks. "
        "Use public documentation for technical explanations, never as proof "
        "that the student's deployment succeeded. Prefer the latest dated "
        "verified record when updating completion status; retain earlier "
        "results as historical observations. An earlier pending note must not "
        "override a later successful run record. Missing evidence is not itself "
        "a failed test: report material gaps once without inventing an outcome."
        "\n\nFigures and integrity: include real supplied Task 1/2 interface "
        "screenshots and, only if available, the Task 3 HTTPS/access-control "
        "screenshot. Preserve the visible browser address bar and add captions "
        "describing what each figure shows; add a limitation only when needed "
        "to prevent a specific misinterpretation. A filename alone "
        "is not an accessible image: embed only genuinely available supplied "
        "image content; otherwise cite the evidence file and explicitly state "
        "the availability gap once, without inventing an image or a broken "
        "image reference. If the task specifies a separately prepared screenshot "
        "appendix for final editing, use its supplied figure IDs without empty "
        "figure boxes or repeated editorial reminders. Never simulate "
        "screenshots, terminal logs, certificate "
        "issuance, test passes, or a successful HTTPS URL. Do not substitute "
        "another project's deployment. Use only supplied names, addresses, "
        "domains, versions, and measurements; omit or flag unknown details. "
        "Exclude API keys, passwords, tokens, verification codes, and other "
        "secret values even if present in input."
        "\n\nLength and presentation: the entire report must fit within 20 "
        "A4 pages, including any cover, contents, figures, tables, references, "
        "and appendices, or a smaller limit requested by the user. Budget "
        "space for the actual evidence, prefer concise explanations and short "
        "log excerpts, and use readable print typography with sensible page "
        "breaks. Do not meet the limit by clipping or hiding content. Do not "
        "claim the rendered page count was verified unless a supplied check "
        "establishes it."
    )
    user_prompt = "\n\n".join(
        [
            "[Assignment Task]\n" + task_text.strip(),
            "[Prepared Context]\n" + context_bundle.strip(),
            "[Search Citations]\n" + format_citations(search),
            "[Options]\n" + json.dumps(options, sort_keys=True),
            "[Output Contract]\n" + output_instruction,
        ]
    )
    return system_prompt, user_prompt

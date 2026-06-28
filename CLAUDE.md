# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A serverless AWS pipeline that monthly downloads index constituent holdings for multiple indexes, enriches them with currency data, and stores the output in S3.

**Stack:** Python 3.12 Lambdas · AWS CDK (Python) · S3 · EventBridge · SNS · SQS (DLQs only) · CloudWatch  
**Package manager:** `uv`

Read `PIPELINE.md` for the full pipeline architecture, module API reference, and instructions for adding a new index.

## Commands

```bash
# Install all dependencies (runtime + infra)
uv sync

# Synthesize CloudFormation template
cd infra && cdk synth --context alertEmail=you@example.com --context googleSheetId=<id>

# Deploy all resources
cd infra && cdk deploy --context alertEmail=you@example.com --context googleSheetId=<id>

# Destroy (note: S3 bucket has RETAIN removal policy and won't be deleted)
cd infra && cdk destroy

# Manually trigger the pipeline outside the monthly schedule
uv run python trigger_aws.py --index stoxx600
uv run python trigger_aws.py --all

# Redrive failed events from DLQs
uv run python redrive.py                        # interactive: all queues
uv run python redrive.py --queue parser         # interactive: one queue
uv run python redrive.py --index_id stoxx600    # filter by index across all queues
uv run python redrive.py --all                  # non-interactive: redrive everything

# Run the full pipeline locally
uv run python run_local.py --index stoxx600
uv run python run_local.py --index msci_world
uv run python run_local.py --index msci_europe_hedged

# Run a single step
uv run python run_local.py --index stoxx600 --step parse --input output/pdf/STOXX_2026-05-01.pdf
```

## Key Non-Obvious Details

- **Shared logic lives in `pipeline/`**, not in Lambda handlers. Handlers are thin wrappers (~15 lines). All core functions are importable locally without AWS.
- **Two Lambda Layers**: `PipelineLayer` copies `pipeline/` into `/opt/python/`; `DepsLayer` pip-installs all runtime deps (built via Docker at synth time). Handler zips contain only `handler.py`.
- **Deps layer is generated at synth time**: `_export_lambda_deps()` in `pipeline_stack.py` runs `uv export --only-group=lambda` to produce `infra/lambda/_deps/requirements.txt`, then Docker pip-installs it. CDK caches the layer by content hash — it only rebuilds when deps change.
- **Bumping a runtime dep**: edit `[dependency-groups].lambda` in `pyproject.toml` → `uv lock` → next `cdk synth` rebuilds the layer automatically.
- **Regex order matters**: `SUPERSECTORS` and `COUNTRIES` in `pipeline/parse.py` are sorted longest-first to prevent partial substring matches.
- **Both `alertEmail` and `googleSheetId`** are required at CDK deploy time — missing either raises `ValueError` immediately.
- **Triggers are push-based, not poll-based**: EventBridge invokes Downloader directly; S3 event notifications invoke Parser/Processor/Uploader directly. There are no main SQS queues — only DLQs that receive events after all Lambda retries are exhausted (`retry_attempts=2`).
- **Memory/timeout** per Lambda: Downloader 128 MB/60s, Parser 512 MB/120s (PDF-heavy), Processor 128 MB/30s, Uploader 128 MB/180s.
- **S3 lifecycle**: all prefixes (pdf/, xls/, raw-csv/, processed-csv/) expire after 365 days.
- **STOXX and iShares may block automated downloads** (403). The downloader spoofs a browser User-Agent; an Elastic IP may be needed.

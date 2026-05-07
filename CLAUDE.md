# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A serverless AWS pipeline that monthly downloads index constituent holdings for multiple indexes, enriches them with currency data, and stores the output in S3.

**Stack:** Python 3.12 Lambdas · AWS CDK (Python) · S3 · EventBridge · SNS · SQS DLQs · CloudWatch  
**Package manager:** `uv`

See @PIPELINE.md for the full pipeline architecture, module API reference, and instructions for adding a new index.

## Commands

```bash
# Synthesize CloudFormation template
cd infra && cdk synth --context alertEmail=you@example.com --context googleSheetId=<id>

# Deploy all resources
cd infra && cdk deploy --context alertEmail=you@example.com --context googleSheetId=<id>

# Destroy (note: S3 bucket has RETAIN removal policy and won't be deleted)
cd infra && cdk destroy

# Run the full pipeline locally
uv run python run_local.py --index stoxx600
uv run python run_local.py --index msci_world
uv run python run_local.py --index msci_europe_hedged

# Run a single step
uv run python run_local.py --index stoxx600 --step parse --input output/pdf/STOXX_2026-05-01.pdf
```

## Key Non-Obvious Details

- **Shared logic lives in `pipeline/`**, not in Lambda handlers. Handlers are thin wrappers (~15 lines). All core functions are importable locally without AWS.
- **CDK bundler** (`_PipBundler` in `pipeline_stack.py`): pip-installs each Lambda's `requirements.txt` locally (no Docker), then copies `pipeline/` into the bundle. Falls back to Docker if local install fails.
- **`Code.from_asset` uses `REPO_ROOT`** (not the Lambda subdirectory) so Docker bundling also has access to `pipeline/`.
- **Regex order matters**: `SUPERSECTORS` and `COUNTRIES` in `pipeline/parse.py` are sorted longest-first to prevent partial substring matches.
- **Both `alertEmail` and `googleSheetId`** are required at CDK deploy time — missing either raises `ValueError` immediately.
- **Memory/timeout** per Lambda: Downloader 128 MB/60s, Parser 512 MB/120s (PDF-heavy), Processor 128 MB/30s.
- **S3 lifecycle**: PDFs expire after 90 days; all csv prefixes are retained indefinitely.
- **STOXX and iShares may block automated downloads** (403). The downloader spoofs a browser User-Agent; an Elastic IP may be needed.

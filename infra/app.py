import os
from pathlib import Path

import aws_cdk as cdk
from dotenv import load_dotenv
from stacks.pipeline_stack import PipelineStack

# Load .env into os.environ (only fills vars not already set — lowest priority)
load_dotenv(Path(__file__).parent / ".env")

app = cdk.App()


def _get(context_key: str, env_key: str) -> str | None:
    # CDK -c flag takes precedence over everything
    return app.node.try_get_context(context_key) or os.environ.get(env_key)


alert_email = _get("alertEmail", "ALERT_EMAIL")
if not alert_email:
    raise ValueError("alertEmail is required — set via -c alertEmail=x, $ALERT_EMAIL, or infra/.env")

google_sheet_id = _get("googleSheetId", "GOOGLE_SHEET_ID")
if not google_sheet_id:
    raise ValueError("googleSheetId is required — set via -c googleSheetId=x, $GOOGLE_SHEET_ID, or infra/.env")

stack = PipelineStack(
    app, "AssetMapping",
    alert_email=alert_email,
    google_sheet_id=google_sheet_id,
    env=cdk.Environment(
        account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
        region=os.environ.get("CDK_DEFAULT_REGION", "eu-west-1"),
    ),
)

cdk.Tags.of(stack).add("application", "AssetMapping")
cdk.Tags.of(stack).add("environment", "prod")

app.synth()

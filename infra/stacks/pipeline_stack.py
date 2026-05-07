import shutil
import subprocess
from pathlib import Path

import aws_cdk as cdk
import jsii
from aws_cdk import (
    Duration,
    ILocalBundling,
    RemovalPolicy,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_lambda_event_sources as event_sources,
    aws_s3 as s3,
    aws_sns as sns,
    aws_sns_subscriptions as subscriptions,
    aws_sqs as sqs,
    aws_ssm as ssm,
)
from constructs import Construct

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@jsii.implements(ILocalBundling)
class _PipBundler:
    """Installs requirements.txt with pip locally and copies the pipeline package."""

    def __init__(self, repo_root: Path, dir_name: str) -> None:
        self._root = repo_root
        self._dir_name = dir_name

    def try_bundle(self, output_dir: str, options: cdk.BundlingOptions = None) -> bool:
        try:
            entry = self._root / self._dir_name
            reqs = entry / "requirements.txt"
            has_deps = reqs.exists() and any(
                ln.strip() and not ln.startswith("#")
                for ln in reqs.read_text().splitlines()
            )
            if has_deps:
                subprocess.run(
                    [
                        "pip", "install", "-r", "requirements.txt", "-t", output_dir,
                        "--platform", "manylinux_2_28_x86_64",
                        "--python-version", "312",
                        "--implementation", "cp",
                        "--only-binary", ":all:",
                        "--no-cache-dir",
                        "--quiet",
                    ],
                    cwd=str(entry),
                    check=True,
                )
            for py_file in entry.glob("*.py"):
                shutil.copy(py_file, output_dir)
            shutil.copytree(self._root / "pipeline", Path(output_dir) / "pipeline", dirs_exist_ok=True)
            return True
        except Exception:
            return False


def _fn(
    scope: Construct,
    id: str,
    *,
    entry: Path,
    runtime: lambda_.Runtime,
    **kwargs,
) -> lambda_.Function:
    """Create a Lambda Function with local pip bundling."""
    dir_name = entry.name
    return lambda_.Function(
        scope, id,
        runtime=runtime,
        handler="handler.handler",
        code=lambda_.Code.from_asset(
            str(REPO_ROOT),
            bundling=cdk.BundlingOptions(
                image=runtime.bundling_image,
                local=_PipBundler(REPO_ROOT, dir_name),  # type: ignore[arg-type]
                # Docker fallback (used only if local bundling returns False)
                command=[
                    "bash", "-c",
                    f"pip install -r /asset-input/{dir_name}/requirements.txt -t /asset-output"
                    f" && cp /asset-input/{dir_name}/*.py /asset-output"
                    f" && cp -r /asset-input/pipeline /asset-output/pipeline",
                ],
            ),
        ),
        **kwargs,
    )


class PipelineStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, *, alert_email: str, google_sheet_id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # ── S3 ────────────────────────────────────────────────────────────────
        bucket = s3.Bucket(
            self, "Holdings",
            removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[
                s3.LifecycleRule(prefix="pdf/", expiration=Duration.days(90))
            ],
        )

        # ── SNS alert topic ───────────────────────────────────────────────────
        alert_topic = sns.Topic(self, "Alerts", display_name="STOXX 600 Pipeline Alerts")
        alert_topic.add_subscription(subscriptions.EmailSubscription(alert_email))  # type: ignore[arg-type]

        # ── Shared helpers ────────────────────────────────────────────────────
        def make_dlq(name: str) -> sqs.Queue:
            dlq = sqs.Queue(self, f"{name}DLQ", retention_period=Duration.days(14))
            cloudwatch.Alarm(
                self, f"{name}DLQAlarm",
                metric=dlq.metric_approximate_number_of_messages_visible(),
                threshold=1,
                evaluation_periods=1,
                alarm_description=f"STOXX 600 {name} DLQ has messages — invocation failed after retries",
            ).add_alarm_action(cw_actions.SnsAction(alert_topic))  # type: ignore[arg-type]
            return dlq

        def wire_error_alarm(fn: lambda_.Function, name: str) -> None:
            cloudwatch.Alarm(
                self, f"{name}ErrorAlarm",
                metric=fn.metric_errors(period=Duration.minutes(5)),
                threshold=1,
                evaluation_periods=1,
                alarm_description=f"STOXX 600 {name} Lambda raised an error",
            ).add_alarm_action(cw_actions.SnsAction(alert_topic))  # type: ignore[arg-type]

        runtime = lambda_.Runtime.PYTHON_3_12

        # ── Lambda 1: Downloader ───────────────────────────────────────────────
        downloader = _fn(
            self, "Downloader",
            entry=REPO_ROOT / "lambda_downloader",
            runtime=runtime,
            environment={"S3_BUCKET": bucket.bucket_name},
            timeout=Duration.seconds(60),
            dead_letter_queue=make_dlq("Downloader"),
        )
        bucket.grant_put(downloader, "pdf/*")
        bucket.grant_put(downloader, "raw-csv/*")
        wire_error_alarm(downloader, "Downloader")

        monthly = events.Schedule.cron(minute="0", hour="6", day="1", month="*", year="*")

        # Monthly on the 1st at 06:00 UTC — STOXX Europe 600
        events.Rule(
            self, "Stoxx600Trigger",
            schedule=monthly,
            targets=[targets.LambdaFunction(  # type: ignore[arg-type, list-item]
                downloader,
                event=events.RuleTargetInput.from_object({"index_id": "stoxx600"}),
            )],
        )

        # Monthly on the 1st at 06:00 UTC — MSCI World (IWDA)
        events.Rule(
            self, "MsciWorldTrigger",
            schedule=monthly,
            targets=[targets.LambdaFunction(  # type: ignore[arg-type, list-item]
                downloader,
                event=events.RuleTargetInput.from_object({"index_id": "msci_world"}),
            )],
        )

        # Monthly on the 1st at 06:00 UTC — MSCI Europe EUR Hedged (IMEAX)
        events.Rule(
            self, "MsciEuropeHedgedTrigger",
            schedule=monthly,
            targets=[targets.LambdaFunction(  # type: ignore[arg-type, list-item]
                downloader,
                event=events.RuleTargetInput.from_object({"index_id": "msci_europe_hedged"}),
            )],
        )

        # ── Lambda 2: Parser ───────────────────────────────────────────────────
        parser = _fn(
            self, "Parser",
            entry=REPO_ROOT / "lambda_parser",
            runtime=runtime,
            environment={"S3_BUCKET": bucket.bucket_name},
            timeout=Duration.seconds(120),
            memory_size=512,
            dead_letter_queue=make_dlq("Parser"),
        )
        bucket.grant_read(parser, "pdf/*")
        bucket.grant_put(parser, "raw-csv/*")
        parser.add_event_source(
            event_sources.S3EventSource(
                bucket,
                events=[s3.EventType.OBJECT_CREATED],
                filters=[s3.NotificationKeyFilter(prefix="pdf/")],
            )
        )
        wire_error_alarm(parser, "Parser")

        # ── Lambda 3: Processor ────────────────────────────────────────────────
        processor = _fn(
            self, "Processor",
            entry=REPO_ROOT / "lambda_processor",
            runtime=runtime,
            environment={"S3_BUCKET": bucket.bucket_name},
            timeout=Duration.seconds(30),
            dead_letter_queue=make_dlq("Processor"),
        )
        bucket.grant_read(processor, "raw-csv/*")
        bucket.grant_put(processor, "processed-csv/*")
        processor.add_event_source(
            event_sources.S3EventSource(
                bucket,
                events=[s3.EventType.OBJECT_CREATED],
                filters=[s3.NotificationKeyFilter(prefix="raw-csv/")],
            )
        )
        wire_error_alarm(processor, "Processor")

        # ── Lambda 4: Uploader ─────────────────────────────────────────────────
        credentials_param_name = "/iuk/ticker-values/google-credentials"
        uploader = _fn(
            self, "Uploader",
            entry=REPO_ROOT / "lambda_uploader",
            runtime=runtime,
            environment={
                "S3_BUCKET": bucket.bucket_name,
                "GOOGLE_SHEET_ID": google_sheet_id,
                "GOOGLE_CREDENTIALS_PARAM": credentials_param_name,
            },
            timeout=Duration.seconds(60),
            dead_letter_queue=make_dlq("Uploader"),
        )
        bucket.grant_read(uploader, "processed-csv/*")
        uploader.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameter"],
                resources=[
                    self.format_arn(
                        service="ssm",
                        resource="parameter",
                        resource_name=credentials_param_name.lstrip("/"),
                    )
                ],
            )
        )
        uploader.add_event_source(
            event_sources.S3EventSource(
                bucket,
                events=[s3.EventType.OBJECT_CREATED],
                filters=[s3.NotificationKeyFilter(prefix="processed-csv/")],
            )
        )
        wire_error_alarm(uploader, "Uploader")

        # ── Outputs ───────────────────────────────────────────────────────────
        cdk.CfnOutput(self, "BucketName", value=bucket.bucket_name)
        cdk.CfnOutput(self, "AlertTopicArn", value=alert_topic.topic_arn)

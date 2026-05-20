import subprocess
import sys
from pathlib import Path

import aws_cdk as cdk
from aws_cdk import (
    Duration,
    RemovalPolicy,
    aws_cloudwatch,
    aws_cloudwatch_actions,
    aws_events,
    aws_events_targets,
    aws_iam,
    aws_lambda,
    aws_lambda_event_sources,
    aws_logs,
    aws_s3,
    aws_s3_notifications,
    aws_sns,
    aws_sns_subscriptions,
    aws_sqs,
)
from constructs import Construct

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LAMBDA_BASE = REPO_ROOT / "infra" / "lambda"
_LAYER_DIR = LAMBDA_BASE / "_deps"

sys.path.insert(0, str(REPO_ROOT))
from pipeline.download import Downloader  # noqa: E402


def _export_lambda_deps() -> None:
    _LAYER_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "uv", "export",
            "--only-group=lambda",
            "--no-hashes", "--no-annotate", "--no-header",
            f"--output-file={_LAYER_DIR / 'requirements.txt'}",
            f"--project={REPO_ROOT}",
        ],
        check=True, cwd=REPO_ROOT,
    )


_export_lambda_deps()


class _DownloaderTriggers(cdk.NestedStack):
    def __init__(self, scope: Construct, id: str, *, queue: aws_sqs.Queue, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        monthly = aws_events.Schedule.cron(minute="0", hour="6", day="28", month="*", year="*")
        for index_id in Downloader.index_ids():
            rule_id = "".join(part.capitalize() for part in index_id.split("_")) + "Trigger"
            aws_events.Rule(
                self, rule_id,
                schedule=monthly,
                targets=[aws_events_targets.SqsQueue(  # type: ignore[arg-type]
                    queue,
                    message=aws_events.RuleTargetInput.from_object({"index_id": index_id}),
                )],
            )


class PipelineStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, *, alert_email: str, google_sheet_id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # ── Alerts ────────────────────────────────────────────────────────────
        alert_topic = aws_sns.Topic(self, "AlertTopic", display_name="Asset Mapping Pipeline Alerts")
        alert_topic.add_subscription(aws_sns_subscriptions.EmailSubscription(alert_email))  # type: ignore[arg-type]

        # ── S3 ────────────────────────────────────────────────────────────────
        bucket = aws_s3.Bucket(
            self, "Holdings",
            removal_policy=RemovalPolicy.DESTROY,
            lifecycle_rules=[
                aws_s3.LifecycleRule(prefix="pdf/", expiration=Duration.days(365)),
                aws_s3.LifecycleRule(prefix="xls/", expiration=Duration.days(365)),
                aws_s3.LifecycleRule(prefix="raw-csv/", expiration=Duration.days(365)),
                aws_s3.LifecycleRule(prefix="processed-csv/", expiration=Duration.days(365)),
            ],
        )

        runtime = aws_lambda.Runtime.PYTHON_3_12

        # ── Lambda Layers ──────────────────────────────────────────────────────
        pipeline_layer = aws_lambda.LayerVersion(
            self, "PipelineLayer",
            code=aws_lambda.Code.from_asset(
                str(REPO_ROOT / "pipeline"),
                bundling=cdk.BundlingOptions(
                    image=runtime.bundling_image,
                    command=[
                        "bash", "-c",
                        "mkdir -p /asset-output/python"
                        " && cp -r /asset-input /asset-output/python/pipeline",
                    ],
                ),
            ),
            compatible_runtimes=[runtime],
            compatible_architectures=[aws_lambda.Architecture.ARM_64],
            description="Shared pipeline package",
        )

        deps_layer = aws_lambda.LayerVersion(
            self, "DepsLayer",
            code=aws_lambda.Code.from_asset(
                str(_LAYER_DIR),
                bundling=cdk.BundlingOptions(
                    image=runtime.bundling_image,
                    platform="linux/arm64",
                    command=[
                        "bash", "-c",
                        "pip install --target /asset-output/python"
                        " -r /asset-input/requirements.txt",
                    ],
                ),
            ),
            compatible_runtimes=[runtime],
            compatible_architectures=[aws_lambda.Architecture.ARM_64],
            description="Lambda runtime dependencies",
        )

        self._runtime = runtime
        self._pipeline_layer = pipeline_layer
        self._deps_layer = deps_layer

        # ── Lambda 1: Downloader ───────────────────────────────────────────────
        downloader_timeout = Duration.seconds(60)
        downloader_queue, _ = self.make_queue("Downloader", downloader_timeout, alert_topic)
        downloader = self.build_lambda(
            "Downloader",
            environment={"S3_BUCKET": bucket.bucket_name},
            timeout=downloader_timeout,
            description="Downloads constituents from source URLs and saves to S3",
        )
        downloader.add_event_source(
            aws_lambda_event_sources.SqsEventSource(downloader_queue, batch_size=1)
        )
        bucket.grant_put(downloader, "pdf/*")
        bucket.grant_put(downloader, "xls/*")
        bucket.grant_put(downloader, "raw-csv/*")

        _DownloaderTriggers(self, "DownloaderTriggers", queue=downloader_queue)

        # ── Lambda 2: Parser ───────────────────────────────────────────────────
        parser_timeout = Duration.seconds(120)
        parser_queue, _ = self.make_queue("Parser", parser_timeout, alert_topic)
        parser = self.build_lambda(
            "Parser",
            environment={"S3_BUCKET": bucket.bucket_name},
            timeout=parser_timeout,
            memory_size=512,
            description="Parses downloaded files (in formats other thanf CSV) from S3 and saves raw CSVs back to S3",
        )
        bucket.grant_read(parser, "pdf/*")
        bucket.grant_read(parser, "xls/*")
        bucket.grant_put(parser, "raw-csv/*")
        for prefix in ("pdf/", "xls/"):
            bucket.add_event_notification(
                aws_s3.EventType.OBJECT_CREATED,
                aws_s3_notifications.SqsDestination(parser_queue),  # type: ignore[arg-type]
                aws_s3.NotificationKeyFilter(prefix=prefix),
            )
        parser.add_event_source(
            aws_lambda_event_sources.SqsEventSource(parser_queue, batch_size=1)
        )

        # ── Lambda 3: Processor ────────────────────────────────────────────────
        processor_timeout = Duration.seconds(30)
        processor_queue, _ = self.make_queue("Processor", processor_timeout, alert_topic)
        processor = self.build_lambda(
            "Processor",
            environment={"S3_BUCKET": bucket.bucket_name},
            timeout=processor_timeout,
            description="Processes raw CSVs from S3 and saves cleaned CSVs in standard format back to S3",
        )
        bucket.grant_read(processor, "raw-csv/*")
        bucket.grant_put(processor, "processed-csv/*")
        bucket.add_event_notification(
            aws_s3.EventType.OBJECT_CREATED,
            aws_s3_notifications.SqsDestination(processor_queue),  # type: ignore[arg-type]
            aws_s3.NotificationKeyFilter(prefix="raw-csv/"),
        )
        processor.add_event_source(
            aws_lambda_event_sources.SqsEventSource(processor_queue, batch_size=1)
        )

        # ── Lambda 4: Uploader ─────────────────────────────────────────────────
        credentials_param_name = "/iuk/ticker-values/google-credentials"
        uploader_timeout = Duration.seconds(60)
        uploader_queue, _ = self.make_queue("Uploader", uploader_timeout, alert_topic)
        uploader = self.build_lambda(
            "Uploader",
            environment={
                "S3_BUCKET": bucket.bucket_name,
                "GOOGLE_SHEET_ID": google_sheet_id,
                "GOOGLE_CREDENTIALS_PARAM": credentials_param_name,
            },
            timeout=uploader_timeout,
            description="Uploads processed CSVs from S3 to Google Sheets",
        )
        bucket.grant_read(uploader, "processed-csv/*")
        uploader.add_to_role_policy(
            aws_iam.PolicyStatement(
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
        bucket.add_event_notification(
            aws_s3.EventType.OBJECT_CREATED,
            aws_s3_notifications.SqsDestination(uploader_queue),  # type: ignore[arg-type]
            aws_s3.NotificationKeyFilter(prefix="processed-csv/"),
        )
        uploader.add_event_source(
            aws_lambda_event_sources.SqsEventSource(
                uploader_queue,
                batch_size=10,
                report_batch_item_failures=True,
            )
        )

        cdk.CfnOutput(self, "BucketName", value=bucket.bucket_name)

    def make_queue(self, name: str, lambda_timeout: Duration, alert_topic: aws_sns.Topic) -> tuple[aws_sqs.Queue, aws_sqs.Queue]:
        dlq = aws_sqs.Queue(
            self, f"{name}DLQ",
            retention_period=Duration.days(14),
        )
        alarm = aws_cloudwatch.Alarm(
            self, f"{name}DLQAlarm",
            metric=dlq.metric_approximate_number_of_messages_visible(
                statistic="Maximum",
                period=Duration.minutes(5),
            ),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=aws_cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=aws_cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        alarm.add_alarm_action(aws_cloudwatch_actions.SnsAction(alert_topic))  # type: ignore[arg-type]
        queue = aws_sqs.Queue(
            self, f"{name}Queue",
            # AWS recommends visibility_timeout >= 6x lambda timeout to avoid
            # the message becoming visible while Lambda is still executing.
            visibility_timeout=Duration.seconds(lambda_timeout.to_seconds() * 6),
            dead_letter_queue=aws_sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=dlq,
            ),
        )
        return queue, dlq

    def build_lambda(self, construct_id: str, **kwargs) -> aws_lambda.Function:
        log_group = aws_logs.LogGroup(
            self, f"{construct_id}Logs",
            retention=aws_logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )
        return aws_lambda.Function(
            self, construct_id,
            code=aws_lambda.Code.from_asset(str(LAMBDA_BASE / construct_id.lower())),
            handler="handler.handler",
            runtime=self._runtime,
            architecture=aws_lambda.Architecture.ARM_64,
            layers=[self._pipeline_layer, self._deps_layer],
            log_group=log_group,
            **kwargs,
        )

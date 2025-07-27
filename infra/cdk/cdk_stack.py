from aws_cdk import (
    Stack,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
    aws_s3 as s3,
    aws_iam as iam,
    Duration,
)
from constructs import Construct
import os
from dotenv import load_dotenv

load_dotenv()

# Default to ap-south-1 if not set
DEFAULT_REGION = os.getenv("DEFAULT_AWS_REGION", "ap-south-1")


class CdkStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # Lambda Function from FastAPI app using Docker
        mirror_lambda = _lambda.DockerImageFunction(
            self,
            "MirrorManagementLambda",
            function_name=f"mirror-management-lambda-{DEFAULT_REGION}",
            architecture=_lambda.Architecture.X86_64,
            code=_lambda.DockerImageCode.from_image_asset(
                "../backend",
                file="Dockerfile",
            ),
            memory_size=512,
            timeout=Duration.seconds(30),
            environment={
                "SUPABASE_URL": os.getenv("SUPABASE_URL", ""),
                "SUPABASE_ANON_KEY": os.getenv("SUPABASE_ANON_KEY", ""),
            },
        )

        # Add CloudWatch Logs permissions
        mirror_lambda.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                resources=["arn:aws:logs:*:*:*"],
            )
        )

        # Create API Gateway
        api = apigw.RestApi(
            self,
            "MirrorManagementApi",
            rest_api_name="Mirror Management API",
            description="API for Mirror Management System",
            binary_media_types=[
                "application/pdf",
                "*/*",
            ],  # Enable binary support for PDFs
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["*"],
            ),
        )

        # Create Lambda integration with binary support
        lambda_integration = apigw.LambdaIntegration(
            mirror_lambda,
            proxy=True,  # Enable proxy integration for binary support
            content_handling=apigw.ContentHandling.CONVERT_TO_BINARY,  # Handle binary responses
        )

        # Define API routes
        # Stats endpoint
        stats = api.root.add_resource("stats")
        stats.add_method("GET", lambda_integration)

        # Login endpoint
        login = api.root.add_resource("login")
        login.add_method("POST", lambda_integration)

        # Invoice endpoint with path parameter
        invoice = api.root.add_resource("invoice")
        invoice_with_id = invoice.add_resource("{order_id}")
        invoice_with_id.add_method("GET", lambda_integration)

        # S3 bucket permissions
        bucket = s3.Bucket.from_bucket_name(
            self, "MirrorManagementBucket", "mirror-management-backend"
        )
        bucket.grant_read_write(mirror_lambda)

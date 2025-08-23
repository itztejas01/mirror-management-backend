from aws_cdk import (
    Stack,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
    aws_iam as iam,
    Duration,
)
from constructs import Construct
import os

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
            memory_size=1024,
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
                "application/octet-stream",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ],
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=[
                    "Content-Type",
                    "X-Amz-Date",
                    "Authorization",
                    "X-Api-Key",
                    "X-Amz-Security-Token",
                    "X-Amz-User-Agent",
                    "Accept",
                    "*",
                ],
                allow_credentials=True,
                max_age=Duration.seconds(300),
            ),
        )

        # Create Lambda integration for JSON endpoints
        json_lambda_integration = apigw.LambdaIntegration(
            mirror_lambda,
            proxy=True,
        )

        # Create Lambda integration for PDF endpoints with binary support
        pdf_lambda_integration = apigw.LambdaIntegration(
            mirror_lambda,
            proxy=True,
            content_handling=apigw.ContentHandling.CONVERT_TO_BINARY,
        )

        # Create Lambda integration for Excel endpoints with binary support
        excel_lambda_integration = apigw.LambdaIntegration(
            mirror_lambda,
            proxy=True,
            content_handling=apigw.ContentHandling.CONVERT_TO_BINARY,
        )

        # Define method responses for JSON endpoints
        json_method_response = [
            apigw.MethodResponse(
                status_code="200",
                response_parameters={
                    "method.response.header.Access-Control-Allow-Headers": True,
                    "method.response.header.Access-Control-Allow-Origin": True,
                    "method.response.header.Access-Control-Allow-Methods": True,
                },
                response_models={
                    "application/json": apigw.Model.EMPTY_MODEL,
                },
            )
        ]

        # Define method responses for PDF endpoints
        pdf_method_response = [
            apigw.MethodResponse(
                status_code="200",
                response_parameters={
                    "method.response.header.Access-Control-Allow-Headers": True,
                    "method.response.header.Access-Control-Allow-Origin": True,
                    "method.response.header.Access-Control-Allow-Methods": True,
                    "method.response.header.Content-Type": True,
                    "method.response.header.Content-Disposition": True,
                },
                response_models={
                    "application/pdf": apigw.Model.EMPTY_MODEL,
                },
            )
        ]

        # Define method responses for Excel endpoints
        excel_method_response = [
            apigw.MethodResponse(
                status_code="200",
                response_parameters={
                    "method.response.header.Access-Control-Allow-Headers": True,
                    "method.response.header.Access-Control-Allow-Origin": True,
                    "method.response.header.Access-Control-Allow-Methods": True,
                    "method.response.header.Content-Type": True,
                    "method.response.header.Content-Disposition": True,
                },
                response_models={
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": apigw.Model.EMPTY_MODEL,
                },
            )
        ]

        # Stats endpoint (JSON)
        stats = api.root.add_resource("stats")
        stats.add_method(
            "GET",
            json_lambda_integration,
            method_responses=json_method_response,
        )

        latest_invoice_number = api.root.add_resource("latest-invoice-number")
        latest_invoice_number.add_method(
            "GET",
            json_lambda_integration,
            method_responses=json_method_response,
        )

        # Login endpoint (JSON)
        login = api.root.add_resource("login")
        login.add_method(
            "POST",
            json_lambda_integration,
            method_responses=json_method_response,
        )

        # Invoice endpoint with path parameter (PDF)
        invoice = api.root.add_resource("invoice")
        invoice_with_id = invoice.add_resource("{order_id}")
        invoice_with_id.add_method(
            "GET",
            pdf_lambda_integration,
            method_responses=pdf_method_response,
        )

        # Size sheet endpoint (PDF, POST)
        size_sheet = api.root.add_resource("size-sheet")
        size_sheet_with_id = size_sheet.add_resource("{customer_id}")
        size_sheet_with_id.add_method(
            "POST",
            pdf_lambda_integration,
            method_responses=pdf_method_response,
        )

        # Size sheet Excel endpoint (XLSX, POST)
        size_sheet_excel = api.root.add_resource("size-sheet-excel")
        size_sheet_excel_with_id = size_sheet_excel.add_resource("{customer_id}")
        size_sheet_excel_with_id.add_method(
            "POST",
            excel_lambda_integration,
            method_responses=excel_method_response,
        )

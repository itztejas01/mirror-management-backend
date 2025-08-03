# GitHub Actions CDK Deployment Workflow

This workflow automatically deploys the CDK stack when code is pushed to the main branch.

## Prerequisites

Before using this workflow, you need to set up the following GitHub repository secrets:

### Required Secrets

1. **AWS_ACCOUNT_ID**: Your AWS Account ID
2. **AWS_ACCESS_KEY_ID**: AWS Access Key ID for deployment
3. **AWS_SECRET_ACCESS_KEY**: AWS Secret Access Key for deployment
4. **SUPABASE_URL**: Your Supabase project URL
5. **SUPABASE_ANON_KEY**: Your Supabase anonymous key

### Setting up GitHub Secrets

1. Go to your GitHub repository
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret** for each required secret
4. Add the secrets with the exact names listed above

### AWS IAM Permissions

The AWS credentials used should have the following permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "cloudformation:*",
        "lambda:*",
        "apigateway:*",
        "iam:*",
        "logs:*",
        "s3:*",
        "ecr:*"
      ],
      "Resource": "*"
    }
  ]
}
```

## Workflow Details

The workflow performs the following steps:

1. **Checkout**: Clones the repository
2. **Setup Python**: Installs Python 3.11
3. **Configure AWS**: Sets up AWS credentials
4. **Install CDK**: Installs AWS CDK globally
5. **Install Dependencies**: Installs Python dependencies from `infra/requirements-infra.txt`
6. **Bootstrap CDK**: Bootstraps CDK in the target AWS account/region (if needed)
7. **Synthesize**: Generates CloudFormation templates
8. **Deploy**: Deploys the CDK stack
9. **Get API URL**: Retrieves and displays the API Gateway URL

## Manual Deployment

You can also trigger the workflow manually:

1. Go to **Actions** tab in your repository
2. Select **Deploy CDK Stack** workflow
3. Click **Run workflow**
4. Select the branch and click **Run workflow**

## Environment Variables

The workflow uses the following environment variables:

- `AWS_REGION`: Set to `ap-south-1` (can be modified in the workflow file)
- `CDK_DEFAULT_ACCOUNT`: Set from `AWS_ACCOUNT_ID` secret
- `CDK_DEFAULT_REGION`: Set to `ap-south-1`

## Troubleshooting

### Common Issues

1. **CDK Bootstrap Error**: If you get a bootstrap error, ensure your AWS credentials have sufficient permissions
2. **Environment Variables**: Make sure all required secrets are set in GitHub
3. **Python Dependencies**: Ensure `infra/requirements-infra.txt` is up to date

### Logs

Check the workflow logs in the **Actions** tab for detailed error messages and deployment status.

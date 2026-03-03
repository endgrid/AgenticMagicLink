variable "project_name" {
  description = "Project name prefix for AWS resources"
  type        = string
  default     = "agentic-magic-link"
}

variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "lambda_package_path" {
  description = "Path to zip package containing backend Lambda code"
  type        = string
}

variable "bedrock_model_id" {
  description = "Bedrock model identifier passed to Lambda runtime"
  type        = string
}

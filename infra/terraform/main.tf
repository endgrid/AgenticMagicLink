terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

resource "aws_iam_role" "lambda_exec" {
  name = "${var.project_name}-chat-lambda-exec"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "post_session" {
  function_name = "${var.project_name}-post-session"
  role          = aws_iam_role.lambda_exec.arn
  handler       = "backend.app.lambda_handlers.chat.post_session_handler"
  runtime       = "python3.11"
  filename      = var.lambda_package_path
  source_code_hash = filebase64sha256(var.lambda_package_path)

  environment {
    variables = {
      BEDROCK_MODEL_ID = var.bedrock_model_id
    }
  }
}

resource "aws_lambda_function" "post_message" {
  function_name = "${var.project_name}-post-message"
  role          = aws_iam_role.lambda_exec.arn
  handler       = "backend.app.lambda_handlers.chat.post_message_handler"
  runtime       = "python3.11"
  filename      = var.lambda_package_path
  source_code_hash = filebase64sha256(var.lambda_package_path)

  environment {
    variables = {
      BEDROCK_MODEL_ID = var.bedrock_model_id
    }
  }
}

resource "aws_apigatewayv2_api" "chat_http_api" {
  name          = "${var.project_name}-chat-http"
  protocol_type = "HTTP"

  cors_configuration {
    allow_credentials = false
    allow_headers     = ["*"]
    allow_methods     = ["*"]
    allow_origins     = ["*"]
    max_age           = 300
  }
}

resource "aws_apigatewayv2_integration" "post_session" {
  api_id                 = aws_apigatewayv2_api.chat_http_api.id
  integration_type       = "AWS_PROXY"
  integration_method     = "POST"
  integration_uri        = aws_lambda_function.post_session.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_integration" "post_message" {
  api_id                 = aws_apigatewayv2_api.chat_http_api.id
  integration_type       = "AWS_PROXY"
  integration_method     = "POST"
  integration_uri        = aws_lambda_function.post_message.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "post_session" {
  api_id    = aws_apigatewayv2_api.chat_http_api.id
  route_key = "POST /api/chat/session"
  target    = "integrations/${aws_apigatewayv2_integration.post_session.id}"
}

resource "aws_apigatewayv2_route" "post_message" {
  api_id    = aws_apigatewayv2_api.chat_http_api.id
  route_key = "POST /api/chat/message"
  target    = "integrations/${aws_apigatewayv2_integration.post_message.id}"
}

resource "aws_lambda_permission" "allow_apigw_post_session" {
  statement_id  = "AllowExecutionFromAPIGatewayPostSession"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.post_session.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.chat_http_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "allow_apigw_post_message" {
  statement_id  = "AllowExecutionFromAPIGatewayPostMessage"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.post_message.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.chat_http_api.execution_arn}/*/*"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.chat_http_api.id
  name        = "$default"
  auto_deploy = true
}

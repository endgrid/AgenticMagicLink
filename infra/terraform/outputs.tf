output "api_endpoint" {
  description = "Base endpoint for the deployed HTTP API"
  value       = aws_apigatewayv2_api.chat_http_api.api_endpoint
}

output "api_endpoint" {
  description = "Base endpoint for the deployed HTTP API"
  value       = aws_apigatewayv2_api.chat_http_api.api_endpoint
}

output "session_table_name" {
  description = "DynamoDB table name used for chat session persistence"
  value       = aws_dynamodb_table.sessions.name
}

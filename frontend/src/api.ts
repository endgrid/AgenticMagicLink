import type { ChatMessage, MessageResponse, SessionResponse } from './types';

function getApiBaseUrl(): string {
  const configuredUrl = import.meta.env.VITE_API_BASE_URL;

  if (!configuredUrl || configuredUrl.trim().length === 0) {
    throw new Error('VITE_API_BASE_URL must be configured for this deployment.');
  }

  return configuredUrl.replace(/\/+$/, '');
}

const API_BASE_URL = getApiBaseUrl();

function mapApiError(defaultMessage: string, detail: string): string {
  const normalizedDetail = detail.toLowerCase();

  if (normalizedDetail.includes('account id') || normalizedDetail.includes('account_id')) {
    return 'Invalid account ID. Please provide exactly 12 digits (for example: 123456789012).';
  }

  if (normalizedDetail.includes('role arn') || normalizedDetail.includes('role_arn')) {
    return 'Invalid role ARN. Use a full IAM role ARN, for example: arn:aws:iam::123456789012:role/MyRole.';
  }

  return detail || defaultMessage;
}

async function parseError(response: Response, defaultMessage: string): Promise<Error> {
  let detail = '';

  try {
    const payload = await response.json();
    if (typeof payload?.detail === 'string') {
      detail = payload.detail;
    }
  } catch {
    detail = '';
  }

  return new Error(mapApiError(defaultMessage, detail));
}

export async function createSession(): Promise<SessionResponse> {
  const response = await fetch(`${API_BASE_URL}/api/chat/session`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  });

  if (!response.ok) {
    throw await parseError(response, 'Failed to create a chat session.');
  }

  return response.json();
}

export async function sendMessage(
  sessionId: string,
  message: string,
  messages: ChatMessage[],
): Promise<MessageResponse> {
  const response = await fetch(`${API_BASE_URL}/api/chat/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      message,
      history: messages,
    }),
  });

  if (!response.ok) {
    throw await parseError(response, 'Failed to process chat message.');
  }

  return response.json();
}

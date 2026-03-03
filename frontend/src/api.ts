import type { ChatMessage, MessageResponse, SessionResponse } from './types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

export async function createSession(): Promise<SessionResponse> {
  const response = await fetch(`${API_BASE_URL}/api/chat/session`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  });

  if (!response.ok) {
    throw new Error('Failed to create a chat session.');
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
    throw new Error('Failed to process chat message.');
  }

  return response.json();
}

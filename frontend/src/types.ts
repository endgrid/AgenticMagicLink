export type Role = 'user' | 'assistant';

export interface ChatMessage {
  role: Role;
  content: string;
}

export interface SessionResponse {
  session_id: string;
}

export interface MessageResponse {
  session_id: string;
  messages: ChatMessage[];
}

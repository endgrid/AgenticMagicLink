export type Role = 'user' | 'assistant';

export type NextExpectedInput = 'work_description' | 'account_id' | 'role_arn';

export interface ChatMessage {
  role: Role;
  content: string;
}

export interface SessionResponse {
  session_id: string;
}

export interface MagicLinkScriptPayload {
  content: string;
  checksum_sha256?: string | null;
  version?: string | null;
}

export interface MessageResponse {
  session_id: string;
  messages: ChatMessage[];
  magic_link_script?: MagicLinkScriptPayload | null;
  next_expected_input?: NextExpectedInput | null;
}

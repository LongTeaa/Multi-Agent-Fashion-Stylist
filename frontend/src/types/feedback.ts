export interface DismissPromptRequest {
  client_session_id?: string | null;
}

export interface DismissPromptResponseData {
  cooldown_remaining: number;
  dismissed: boolean;
}

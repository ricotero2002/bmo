export interface Chat {
  thread_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface Message {
  role: "user" | "assistant" | "system" | "data";
  content: string;
  parts?: any;
  created_at: string;
}

export async function fetchChats(userId: string): Promise<Chat[]> {
  const params = new URLSearchParams({ user_id: userId });
  const response = await fetch(`/api/chats?${params}`);
  if (!response.ok) {
    throw new Error("Failed to fetch chats");
  }
  const data = await response.json();
  return data.chats;
}

export async function fetchMessages(threadId: string): Promise<Message[]> {
  const response = await fetch(`/api/chats/${threadId}/messages`);
  if (!response.ok) {
    throw new Error("Failed to fetch messages");
  }
  const data = await response.json();
  return data.messages;
}

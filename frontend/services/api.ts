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

export async function sendFeedback(
  threadId: string,
  score: number,
  messageId?: string,
  userPrompt?: string,
  aiResponse?: string,
  toolsUsed?: any,
  userCorrection?: string
): Promise<string> {
  const payload = {
    thread_id: threadId,
    message_id: messageId,
    user_prompt: userPrompt,
    ai_response: aiResponse,
    tools_used: toolsUsed,
    score: score,
    user_correction: userCorrection
  };

  const response = await fetch('/api/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    throw new Error('Failed to send feedback');
  }

  const data = await response.json();
  return data.feedback_id;
}

export async function fetchDocuments(userId: string) {
  const response = await fetch(`/api/debug/document?user_id=${userId}`);
  if (!response.ok) throw new Error("Failed to fetch documents");
  return response.json();
}

export async function checkIngestionStatus(docId: string) {
  const response = await fetch(`/api/ingestion-status/${docId}`);
  if (!response.ok) throw new Error("Failed to fetch status");
  return response.json();
}

export async function deleteDocument(docId: string, userId: string) {
  const response = await fetch(`/api/delete_file`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ doc_id: docId, user_id: userId })
  });
  if (!response.ok) throw new Error("Failed to delete document");
  return response.json();
}

export async function uploadDocument(file: File, userId: string, date: string) {
  const formData = new FormData();
  formData.append('file', file);
  if (userId) formData.append('user_id', userId);
  if (date) formData.append('document_date', date);

  const response = await fetch('/api/ingest', {
    method: 'POST',
    body: formData
  });
  return response;
}

export async function testSecureEndpoint() {
  try {
    // 1. Pedimos el token al proxy de Auth0
    const res = await fetch('/auth/access-token');

    if (!res.ok) {
      throw new Error(`Falló al obtener el token de Auth0: ${res.statusText}`);
    }

    const data = await res.json();
    const accessToken = data.token;

    // DEBUG: Imprime el token en la consola de tu navegador. 
    // Si ves "eyJ...", es un JWT real. Si ves una cadena corta, sigue siendo un Opaque Token.
    console.log("Access Token obtenido:", accessToken);

    if (!accessToken) {
      throw new Error("El token es null o undefined");
    }

    // 2. Llamamos a FastAPI
    const apiRes = await fetch('http://localhost:8081/api/seguro', {
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json'
      }
    });

    if (!apiRes.ok) {
      const errorData = await apiRes.json();
      throw new Error(`Error de FastAPI: ${JSON.stringify(errorData)}`);
    }

    const finalData = await apiRes.json();
    console.log("¡Respuesta exitosa de FastAPI!", finalData);
    return finalData;

  } catch (error) {
    console.error("Error en testSecureEndpoint:", error);
    return Promise.reject(error);
  }
}

export async function getDocumentChunks(docId: string) {
  const response = await fetch(`/api/debug/document/${docId}/chunks`);
  if (!response.ok) throw new Error("Failed to fetch chunks");
  return response.json();
}

import { createUIMessageStream, createUIMessageStreamResponse } from 'ai';

export async function POST(req: Request) {
    const json = await req.json();
    const messages = json.messages || [];
    const threadId = json.thread_id || "test-thread";
    const userId = json.user_id || "User";
    const baseUrl = process.env.BACKEND_URL;

    if (!baseUrl) {
        console.error('CRITICAL ERROR: BACKEND_URL environment variable is missing.');
        return new Response('Internal Server Error: Missing Configuration', { status: 500 });
    }

    const lastMessage = messages[messages.length - 1];
    const lastMessageText = lastMessage?.parts ? lastMessage.parts.map((p: any) => p.text).join('') : (lastMessage?.content || "");
    
    const payload = {
        message: lastMessageText,
        thread_id: threadId,
        user_info: { user_id: userId },
        prompt_version: "rag_v1"
    };

    const stream = createUIMessageStream({
        execute: async ({ writer }) => {
            const response = await fetch(`${baseUrl}/api/ask/stream`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload),
            });

            const reader = response.body?.getReader();
            if (!reader) return;
            
            const decoder = new TextDecoder();
            let buffer = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n\n");
                buffer = lines.pop() || ""; 

                for (const line of lines) {
                    if (line.startsWith("data: ")) {
                        try {
                            const data = JSON.parse(line.replace("data: ", ""));

                            if (data.type === 'token' && data.content) {
                                // Vercel AI SDK 'text-delta' is typically used for appending text chunks
                                writer.write({ type: 'text-delta', delta: data.content, id: 'main-text' });
                            } else if (data.type === 'status' && data.content) {
                                // Muestra los mensajes de los Agentes mientras "piensan" (transient part)
                                writer.write({ 
                                    type: 'data-status', 
                                    data: { message: data.content }, 
                                    transient: true 
                                });
                            }
                        } catch (e) {
                            // descartar
                        }
                    }
                }
            }
        }
    });

    return createUIMessageStreamResponse({ stream });
}
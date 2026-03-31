import { createUIMessageStream, createUIMessageStreamResponse } from 'ai';

export async function POST(req: Request) {
    const json = await req.json();
    const messages = json.messages || [];
    const threadId = json.threadId || "";
    const userId = json.userId || "User";
    const promptVersion = json.promptVersion || "rag_v2";
    const baseUrl = process.env.BACKEND_URL;

    if (!baseUrl) {
        console.error('CRITICAL ERROR: BACKEND_URL environment variable is missing.');
        return new Response('Internal Server Error: Missing Configuration', { status: 500 });
    }

    const lastMessage = messages[messages.length - 1];
    const lastMessageText = lastMessage?.parts
        ? lastMessage.parts.map((p: any) => p.text).join('')
        : (lastMessage?.content || "");

    const payload = {
        message: lastMessageText,
        thread_id: threadId,
        user_info: { user_id: userId },
        prompt_version: promptVersion
    };

    const stream = createUIMessageStream({
        execute: async ({ writer }) => {
            console.log('[API/CHAT] Execution started');
            try {
                console.log('[API/CHAT] Fetching from backend:', `${baseUrl}/api/ask/stream`);
                console.log('[API/CHAT] Payload:', JSON.stringify(payload));

                const response = await fetch(`${baseUrl}/api/ask/stream`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });

                console.log('[API/CHAT] Backend status:', response.status);

                const reader = response.body?.getReader();
                if (!reader) {
                    console.log('[API/CHAT] No reader from backend');
                    return;
                }

                const decoder = new TextDecoder();
                let buffer = "";
                // Creamos un ID único para este bloque de texto
                const textPartId = `text-${Date.now()}`;
                let hasStartedText = false;

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) {
                        console.log('[API/CHAT] Stream done');
                        break;
                    }

                    const decodedChunk = decoder.decode(value, { stream: true });
                    buffer += decodedChunk;
                    const lines = buffer.split("\n\n");
                    buffer = lines.pop() || "";

                    for (const line of lines) {
                        if (line.startsWith("data: ")) {
                            try {
                                const dataStr = line.replace("data: ", "");
                                const data = JSON.parse(dataStr);
                                console.log('[API/CHAT] Parsed event:', data.type, 'content length:', data.content?.length || 0);

                                if (data.type === 'token' && data.content) {
                                    // Make sure to start the text part
                                    if (!hasStartedText) {
                                        writer.write({ type: 'text-start', id: textPartId });
                                        hasStartedText = true;
                                    }

                                    // 1. Chunk de texto estándar para el AI SDK
                                    writer.write({
                                        type: 'text-delta',
                                        id: textPartId,
                                        delta: data.content
                                    });
                                } else if (data.type === 'status' && data.content) {
                                    // 2. Estado efímero (Transient Data)
                                    writer.write({
                                        type: 'data-status',
                                        data: { message: data.content },
                                        transient: true // CLAVE: No se guarda en el historial
                                    });
                                } else if (data.type === 'thread_id' && data.content) {
                                    // 3. Capturar ID de nuevo hilo y enviarlo al UI
                                    writer.write({
                                        type: 'data-status',
                                        data: { thread_id: data.content },
                                        transient: true
                                    });
                                } else if (data.type === 'error') {
                                    console.error('[API/CHAT] Backend returned error event:', data.content);
                                    throw new Error(data.content);
                                }
                            } catch (e) {
                                console.log('[API/CHAT] Failed to parse line:', line, 'Error:', e);
                            }
                        }
                    }
                }

                if (hasStartedText) {
                    // Cierra el bloque de texto
                    // eslint-disable-next-line @typescript-eslint/ban-ts-comment
                    // @ts-ignore - The types might be slightly strict but this is needed
                    writer.write({ type: 'text-end', id: textPartId });
                }

            } catch (error) {
                console.error("[API/CHAT] Stream error:", error);
            }
            console.log('[API/CHAT] Execution Finished');
        }
    });

    return createUIMessageStreamResponse({ stream });
}
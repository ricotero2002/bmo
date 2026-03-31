'use client';

import { useChat } from '@ai-sdk/react';
import { DefaultChatTransport } from 'ai'; // IMPORTANTE: Agregado
import { useState, useEffect } from 'react';
import { MyUIMessage } from '../types/ai/types';
import { Skeleton } from './ui/skeleton';

interface ChatProps {
    user: { id: string; name: string };
    threadId: string | null;
    promptVersion: string;
    initialMessages?: MyUIMessage[];
    onNewThreadId?: (id: string) => void;
}

export default function ChatInterface({ user, threadId, promptVersion, initialMessages, onNewThreadId }: ChatProps) {
    console.log('[CHAT_UI] Rendering with initialMessages:', initialMessages?.length);
    // 1. Manejo manual del input como indica la nueva doc
    const [input, setInput] = useState('');
    const [agentStatus, setAgentStatus] = useState<string | null>(null);

    // @ts-ignore - Bypass useChat version type discrepancies
    const { messages, sendMessage, setMessages, status } = useChat({
        // @ts-ignore - AI SDK 3.x typing compatibility for generic initialMessages
        initialMessages: initialMessages || [],
        transport: new DefaultChatTransport({
            api: '/api/chat',
        }),
        onData: (dataPart: any) => {
            console.log('[CHAT_UI] onData received:', dataPart);
            if (dataPart?.type === 'data-status') {
                if (dataPart?.data?.thread_id && onNewThreadId) {
                    onNewThreadId(dataPart.data.thread_id);
                } else if (dataPart?.data?.message) {
                    setAgentStatus(dataPart.data.message);
                }
            }
        },
        onFinish: () => {
            setAgentStatus(null);
        }
    });

    // Sincronizar mensajes iniciales o limpiar cuando el usuario explícitamente pide un New Chat (threadId === null)
    useEffect(() => {
        if (initialMessages && initialMessages.length > 0) {
            setMessages(initialMessages);
        } else if (threadId === null) {
            // El usuario clickeó "New Chat", y threadId es explícitamente null.
            // Si estuviéramos recibiendo el thread ID a mitad del stream, threadId ya no sería null
            // y esto no borraría su chat en progreso.
            setMessages([]);
        }
    }, [initialMessages, threadId, setMessages]);

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim()) return;

        // 3. Enviamos variables custom por el body al invocar sendMessage
        // @ts-ignore
        sendMessage(
            { text: input },
            {
                body: {
                    userId: user.id,
                    threadId: threadId || "", // Si no hay, envíamos vacío para crear nuevo
                    promptVersion: promptVersion,
                }
            }
        );
        setInput('');
    };

    return (
        <div className="flex flex-col h-full w-full mx-auto p-4 bg-background text-foreground overflow-hidden rounded-lg shadow-sm border">
            {/* Transient messages displayed ABOVE the chat area */}
            {agentStatus && (status === 'submitted' || status === 'streaming') && (
                <div className="bg-primary/10 border border-primary/20 text-primary px-4 py-2 mb-4 rounded-md text-sm font-medium animate-pulse text-center w-full shadow-sm">
                    ⏳ {agentStatus}
                </div>
            )}
            
            <div className="flex-1 overflow-y-auto space-y-6 scroll-smooth pr-2 pb-4">
                {(messages.length > 0 ? messages : (initialMessages || [])).map((m) => (
                    <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                        <div className="max-w-[85%] space-y-2">
                            <span className="text-xs font-bold opacity-50 block">
                                {m.role === 'user' ? user.name : 'AI Assistant'}
                            </span>

                            {(() => {
                                const mAny = m as any;
                                const contentText = typeof mAny.content === 'string' ? mAny.content : mAny.text || mAny.message || "";
                                
                                // Process non-text parts first
                                const otherParts = (m.parts || []).filter(part => part.type !== 'text').map((part, index) => {
                                    if (part.type === 'reasoning') {
                                        return (
                                            <div key={index} className="text-xs italic text-muted-foreground bg-muted p-2 rounded-md">
                                                🤔 {part.text}
                                            </div>
                                        );
                                    }
                                    if (part.type === 'source-url') {
                                        return (
                                            <div key={index} className="text-xs text-blue-500 mt-1">
                                                🔗 <a href={part.url} target="_blank" rel="noopener noreferrer">
                                                    {part.title || new URL(part.url).hostname}
                                                </a>
                                            </div>
                                        );
                                    }
                                    return null;
                                }).filter(Boolean);

                                return (
                                    <div className="space-y-2">
                                        {/* Texto principal o partes de texto combinadas */}
                                        {contentText.trim() ? (
                                            <div className="p-3 rounded-lg bg-secondary border shadow-sm whitespace-pre-wrap flex flex-col gap-2">
                                                {contentText}
                                            </div>
                                        ) : (m.parts && m.parts.length > 0) ? (
                                            m.parts.filter(p => p.type === 'text').map((p, idx) => (
                                                <div key={idx} className="p-3 rounded-lg bg-secondary border shadow-sm whitespace-pre-wrap">
                                                    {p.text}
                                                </div>
                                            ))
                                        ) : null}

                                        {/* Resto de partes mapeadas */}
                                        {otherParts.length > 0 && (
                                            <div className="flex flex-col gap-2">
                                                {otherParts}
                                            </div>
                                        )}
                                    </div>
                                );
                            })()}
                        </div>
                    </div>
                ))}

                {/* Mostrar esqueleto temporal en el chat mientras esperamos que regrese el primer texto del asistente */}
                {status === 'submitted' && (
                    <div className="flex justify-start">
                        <div className="max-w-[85%] space-y-2 w-full lg:w-[45%]">
                            <span className="text-xs font-bold opacity-50 block">AI Assistant</span>
                            <div className="p-3 rounded-lg bg-secondary border shadow-sm">
                                <div className="space-y-3">
                                    <Skeleton className="h-4 w-full" />
                                    <Skeleton className="h-4 w-[90%]" />
                                    <Skeleton className="h-4 w-[70%]" />
                                </div>
                            </div>
                        </div>
                    </div>
                )}
            </div>

            <form onSubmit={handleSubmit} className="mt-4 flex gap-2 items-center">


                <input
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder="Pregunta algo..."
                    className="flex-1 p-2 rounded-md border bg-muted focus:ring-2 ring-primary"
                    disabled={status !== 'ready' && status !== 'error'}
                />
                <button type="submit" className="bg-primary text-primary-foreground px-4 py-2 rounded-md font-medium" disabled={status !== 'ready' && status !== 'error'}>
                    Enviar
                </button>
            </form>
        </div>
    );
}
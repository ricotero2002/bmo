'use client';

import { useChat } from '@ai-sdk/react';
import { DefaultChatTransport } from 'ai'; // IMPORTANTE: Agregado
import { useState, useEffect } from 'react';
import { MyUIMessage } from '../types/ai/types';
import { Skeleton } from './ui/skeleton';
import ChatFeedback from './ChatFeedback';

interface ChatProps {
    user: { id: string; name: string };
    threadId: string | null;
    promptVersion: string;
    initialMessages?: MyUIMessage[];
    onNewThreadId?: (id: string) => void;
    onStreamingFinished?: () => void;
}

export default function ChatInterface({ user, threadId, promptVersion, initialMessages, onNewThreadId, onStreamingFinished }: ChatProps) {
    console.log('[CHAT_UI] Rendering with initialMessages:', initialMessages?.length);
    // 1. Manejo manual del input como indica la nueva doc
    const [input, setInput] = useState('');
    const [agentStatus, setAgentStatus] = useState<string | null>(null);
    const [currentPlan, setCurrentPlan] = useState<any[] | null>(null);
    const [currentTool, setCurrentTool] = useState<string | null>(null);
    const [isPlanExpanded, setIsPlanExpanded] = useState(false);

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
            } else if (dataPart?.type === 'plan') {
                setCurrentPlan(dataPart.data);
                setCurrentTool(null);
            } else if (dataPart?.type === 'tool-start') {
                setCurrentTool(dataPart.data);
                
                // Si es save_note, extraemos el título para mostrarlo
                if (dataPart.data === 'save_note_to_knowledge_base' && dataPart.input?.title) {
                    setAgentStatus(`Guardando nota: "${dataPart.input.title}"...`);
                } else {
                    setAgentStatus(`Ejecutando: ${dataPart.data}`);
                }
            } else if (dataPart?.type === 'tool-end') {
                // Update plan to mark as done
                if (currentPlan) {
                    setCurrentPlan(prev => prev ? prev.map(step => step.tool === dataPart.data ? { ...step, done: true } : step) : null);
                }
                setCurrentTool(null);
            }
        },
        onFinish: () => {
            setAgentStatus(null);
            if (onStreamingFinished) onStreamingFinished();
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
        setCurrentPlan(null);
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
            {(status === 'submitted' || status === 'streaming') && (
                <div className="mb-4 space-y-2">
                    {/* Renderizamos el PLAN independientemente de los mensajes */}
                    {currentPlan && currentPlan.length > 0 && (
                        <div className="border rounded-md overflow-hidden bg-secondary shadow-sm">
                            <div
                                className="px-3 py-2 text-xs font-medium cursor-pointer hover:bg-secondary/80 flex items-center justify-between"
                                onClick={() => setIsPlanExpanded(!isPlanExpanded)}
                            >
                                <div className="flex items-center gap-2">
                                    <span className="animate-spin inline-block">⚙️</span>
                                    <span>Plan de ejecución ({currentPlan.filter(p => p.done).length}/{currentPlan.length})</span>
                                </div>
                                <span>{isPlanExpanded ? '▼' : '▶'}</span>
                            </div>
                            {isPlanExpanded && (
                                <ul className="px-3 pb-2 text-[11px] space-y-1 opacity-80 border-t pt-2">
                                    {currentPlan.map((step, i) => {
                                        const isExecuting = currentTool === step.tool && !step.done;
                                        let icon = step.done ? '✅' : (isExecuting ? '⏳' : '⬜');
                                        return (
                                            <li key={i} className={`flex items-center gap-1 ${isExecuting ? 'text-primary font-bold' : ''}`}>
                                                <span>{icon}</span> {step.tool}: <span className="italic">{step.reason}</span>
                                            </li>
                                        );
                                    })}
                                </ul>
                            )}
                        </div>
                    )}
                    
                    {/* Status de texto */}
                    {agentStatus && (
                        <div className="bg-primary/10 border border-primary/20 text-primary px-4 py-2 rounded-md text-sm font-medium animate-pulse text-center w-full shadow-sm">
                            ⏳ {agentStatus}
                        </div>
                    )}
                </div>
            )}

            <div className="flex-1 overflow-y-auto space-y-6 scroll-smooth pr-2 pb-4">
                {(messages.length > 0 ? messages : (initialMessages || [])).map((m, idx) => {
                    return (
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
                                                    <div>
                                                        {(() => {
                                                            const mdRegex = /\[([^\]]+)\]\((https?:\/\/[^\s)]*)\)?/g;
                                                            const parts = [];
                                                            let lastIndex = 0;
                                                            let match;

                                                            while ((match = mdRegex.exec(contentText)) !== null) {
                                                                if (match.index > lastIndex) {
                                                                    parts.push(<span key={`text-${lastIndex}`}>{contentText.substring(lastIndex, match.index)}</span>);
                                                                }
                                                                const isComplete = match[0].endsWith(')');
                                                                parts.push(
                                                                    isComplete
                                                                        ? <a key={`link-${match.index}`} href={match[2]} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline font-medium break-all">{match[1]}</a>
                                                                        : <span key={`link-${match.index}`} className="text-blue-500 font-medium opacity-70">🔗 {match[1]}...</span>
                                                                );
                                                                lastIndex = match.index + match[0].length;
                                                            }

                                                            if (lastIndex < contentText.length) {
                                                                parts.push(<span key={`text-${lastIndex}`}>{contentText.substring(lastIndex)}</span>);
                                                            }
                                                            return parts;
                                                        })()}
                                                    </div>
                                                    {/* Chip de seguimiento de Documento Guardado (si detecta "(ID: uuid)") */}
                                                    {contentText.match(/\(ID:\s*([a-f0-9-]+)\)/) && (
                                                        <div
                                                            className="mt-2 text-xs bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 p-2 rounded border border-blue-200 dark:border-blue-800 flex items-center justify-between cursor-pointer hover:bg-blue-100 dark:hover:bg-blue-900/50 transition-colors"
                                                            onClick={() => {
                                                                const match = contentText.match(/\(ID:\s*([a-f0-9-]+)\)/);
                                                                if (match) {
                                                                    alert(`Document ID: ${match[1]}\nPuedes usar este ID en el buscador de la pestaña Documentos para ver su estado.`);
                                                                }
                                                            }}
                                                        >
                                                            <span>📄 Documento en procesamiento</span>
                                                            <span className="font-mono bg-blue-100 dark:bg-blue-800 px-1 rounded">Ver Estado</span>
                                                        </div>
                                                    )}
                                                </div>
                                            ) : (m.parts && m.parts.length > 0) ? (
                                                m.parts.filter((p: any) => p.type === 'text').map((p: any, idx: number) => (
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

                                            {/* Chat Feedback (solo para assistant) */}
                                            {m.role === 'assistant' && threadId && (
                                                <ChatFeedback
                                                    threadId={threadId}
                                                    messageId={m.id}
                                                    userPrompt={(messages[messages.findIndex(x => x.id === m.id) - 1] as any)?.content as string}
                                                    aiResponse={contentText}
                                                    toolsUsed={m.parts?.filter((p: any) => p.type !== 'text')}
                                                />
                                            )}
                                        </div>
                                    );
                                })()}
                            </div>
                        </div>
                    )
                })}

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
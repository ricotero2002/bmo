'use client';

import { useState } from 'react';
import { useChat } from '@ai-sdk/react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { SendIcon, UserIcon, BotIcon, SettingsIcon } from 'lucide-react';

export default function ChatInterface() {
    const [input, setInput] = useState('');
    const [userId, setUserId] = useState('User');
    const [threadId, setThreadId] = useState('thread-123');
    const [statusMessage, setStatusMessage] = useState<string | null>(null);

    const { messages, status, sendMessage } = useChat({
        onData: (dataPart: any) => {
            if (dataPart.type === 'data-status' && dataPart.data?.message) {
                setStatusMessage(dataPart.data.message);
            }
        }
    });

    const isLoading = status === 'submitted' || status === 'streaming';
    
    // Resetear statusMessage cuando termine
    if (!isLoading && statusMessage) setStatusMessage(null);

    const handleFormSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim() || isLoading) return;

        setStatusMessage("Poniéndose en contacto con el Agente...");
        const text = input;
        setInput(''); 

        // Enviamos el mensaje y adjuntamos nuestro config en el body
        await sendMessage(
            { text },
            { body: { thread_id: threadId, user_id: userId } }
        );
    };

    return (
        <div className="flex flex-col h-[700px] w-full max-w-2xl mx-auto border rounded-lg shadow-sm bg-background">
            {/* Panel de Configuración Rápida */}
            <div className="p-3 border-b bg-muted/30 flex gap-4 items-center text-sm">
                <SettingsIcon size={16} className="text-muted-foreground" />
                <div className="flex-1 flex gap-2 items-center">
                    <label className="text-muted-foreground whitespace-nowrap">User ID:</label>
                    <Input 
                        value={userId} 
                        onChange={(e) => setUserId(e.target.value)} 
                        className="h-8 w-32"
                    />
                </div>
                <div className="flex-1 flex gap-2 items-center">
                    <label className="text-muted-foreground whitespace-nowrap">Thread ID:</label>
                    <Input 
                        value={threadId} 
                        onChange={(e) => setThreadId(e.target.value)} 
                        className="h-8 w-32"
                    />
                </div>
            </div>

            {/* Área de Mensajes (Historial en vivo) */}
            <ScrollArea className="flex-1 p-4">
                <div className="flex flex-col gap-4">
                    {messages.map((m) => {
                        // AI SDK => UIMessage doesn't have content anymore, only parts
                        // @ts-ignore
                        const messageText = m.parts ? m.parts.map(p => p.type === 'text' ? p.text : '').join('') : (m.content || '');

                        return (
                            <div
                                key={m.id}
                                className={`flex gap-3 text-sm ${m.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}
                            >
                                {/* Avatar (Usuario o IA) */}
                                <Avatar className="w-8 h-8">
                                    {m.role === 'user' ? (
                                        <div className="bg-primary text-primary-foreground w-full h-full flex items-center justify-center rounded-full">
                                            <UserIcon size={16} />
                                        </div>
                                    ) : (
                                        <div className="bg-muted text-muted-foreground w-full h-full flex items-center justify-center rounded-full">
                                            <BotIcon size={16} />
                                        </div>
                                    )}
                                </Avatar>

                                {/* Burbuja de Chat */}
                                <div
                                    className={`p-3 rounded-lg max-w-[80%] whitespace-pre-wrap ${m.role === 'user'
                                            ? 'bg-primary text-primary-foreground rounded-tr-none'
                                            : 'bg-muted text-foreground rounded-tl-none'
                                        }`}
                                >
                                    {messageText}
                                </div>
                            </div>
                        );
                    })}

                    {/* Mensaje de progreso o transitorio */}
                    {isLoading && statusMessage && (
                        <div className="flex gap-3 text-sm flex-row items-center text-muted-foreground animate-pulse">
                            <BotIcon size={16} className="ml-1" />
                            <span>{statusMessage}</span>
                        </div>
                    )}
                </div>
            </ScrollArea>

            {/* Barra de Input */}
            <div className="p-4 border-t bg-background">
                <form
                    onSubmit={handleFormSubmit}
                    className="flex w-full items-center space-x-2"
                >
                    <Input
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        placeholder="Escribe tu mensaje..."
                        className="flex-1"
                        disabled={isLoading}
                    />
                    <Button type="submit" disabled={isLoading || !input.trim()}>
                        <SendIcon className="h-4 w-4" />
                    </Button>
                </form>
            </div>
        </div>
    );
}
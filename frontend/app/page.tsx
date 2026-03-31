"use client";

import { useState, useEffect } from "react";
import ChatInterface from "@/components/ChatInterface";
import Sidebar from "@/components/Sidebar";
import { useUser } from "@/app/context/UserContext";
import { fetchMessages, Message } from "@/services/api";
import { MyUIMessage } from "@/types/ai/types";
import { generateId } from "ai";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import DocumentManager from "@/components/DocumentManager";

export default function Home() {
  const { userId, setUserId, userName, setUserName } = useUser();
  const queryClient = useQueryClient();
  const [threadId, setThreadId] = useState<string | null>(null);
  const [promptVersion, setPromptVersion] = useState("rag_v2");
  
  // Query para obtener mensajes del thread actual
  const { data: history, isLoading: isLoadingHistory } = useQuery<Message[]>({
    queryKey: ["messages", threadId],
    queryFn: () => fetchMessages(threadId!),
    enabled: !!threadId,
    staleTime: 1000 * 60 * 5, // 5 minutos de cache
  });

  // Modal de Login simple si no hay userId
  const [showLogin, setShowLogin] = useState(false);
  const [tempUserId, setTempUserId] = useState("");
  
  const [showDocumentManager, setShowDocumentManager] = useState(false);

  const [isActivelyLoadingHistory, setIsActivelyLoadingHistory] = useState(false);

  const [initialMessages, setInitialMessages] = useState<MyUIMessage[]>([]);

  useEffect(() => {
    if (!userId || userId === "Anonymous" || userId === "Agustin") {
      setShowLogin(true);
      setTempUserId(userId === "Anonymous" ? "" : userId);
    } else {
      setShowLogin(false);
    }
  }, [userId]);

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    if (tempUserId.trim()) {
      setUserId(tempUserId.trim());
      setUserName(tempUserId.trim());
      setShowLogin(false);
    }
  };

  useEffect(() => {
    if (history) {
      console.log("[HOME] History received from backend:", history);
      const uiMessages: MyUIMessage[] = history.map((msg) => {
        const content = msg.content || "";
        return {
          id: generateId(),
          role: (msg.role === 'data' ? 'assistant' : msg.role) as 'user' | 'assistant' | 'system',
          content: content,
          parts: msg.parts && Array.isArray(msg.parts) && msg.parts.length > 0
            ? msg.parts 
            : [{ type: 'text', text: content }]
        };
      });
      console.log("[HOME] Transformed UI Messages:", uiMessages);
      setInitialMessages(uiMessages);
      setIsActivelyLoadingHistory(false);
    } else if (!threadId) {
      setInitialMessages([]);
      setIsActivelyLoadingHistory(false);
    }
  }, [history, threadId]);

  const handleNewChat = () => {
    if (threadId === null && initialMessages.length === 0) return;
    setThreadId(null);
    setInitialMessages([]);
  };

  const handleSelectChat = (selectedThreadId: string) => {
    if (selectedThreadId === threadId) return;
    setIsActivelyLoadingHistory(true);
    setThreadId(selectedThreadId);
  };

  const handleNewThreadId = (newId: string) => {
    // Cuando el backend avisa que se creó un nuevo hilo, lo seteamos
    // para que los siguientes mensajes vayan ahí
    setThreadId(newId);
    queryClient.invalidateQueries({ queryKey: ['chats'] }); // Actualizar la barra lateral
  };

  if (showLogin) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-zinc-50 dark:bg-black p-4">
        <div className="bg-white dark:bg-zinc-900 p-8 rounded-lg shadow-sm border border-zinc-200 dark:border-zinc-800 w-full max-w-sm">
          <div className="text-center mb-6">
            <img src="/avatar.png" alt="Assistant" className="w-16 h-16 rounded-full mx-auto mb-4 border" />
            <h1 className="text-2xl font-semibold">Welcome Back</h1>
            <p className="text-sm text-zinc-500 mt-2">Introduce tu ID de usuario para continuar.</p>
          </div>
          <form onSubmit={handleLogin} className="flex flex-col gap-4">
            <input 
              value={tempUserId}
              onChange={(e) => setTempUserId(e.target.value)}
              placeholder="Ej: agustin_dev"
              className="p-2 border rounded-md bg-transparent"
              autoFocus
            />
            <button type="submit" className="bg-primary text-primary-foreground py-2 rounded-md font-medium">
              Start Chatting
            </button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-white dark:bg-zinc-950 overflow-hidden text-zinc-900 dark:text-zinc-100">
      <Sidebar 
        currentThreadId={threadId || ""} 
        onSelectChat={handleSelectChat} 
        onNewChat={handleNewChat} 
        onManageDocuments={() => setShowDocumentManager(true)}
      />

      <main className="flex-1 flex flex-col relative">
        {/* Cabecera / Configuracion rápida (Oculta o minimizada) */}
        <header className="h-12 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between px-4 bg-zinc-50/50 dark:bg-zinc-950/50 backdrop-blur-sm z-10 shrink-0">
          <h1 className="text-sm font-medium">
            {threadId ? `Chat: ${threadId.split('-')[0]}...` : "New Conversation"}
          </h1>
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <span>Prompt Version:</span>
            <input 
              value={promptVersion}
              onChange={(e) => setPromptVersion(e.target.value)}
              className="px-2 py-1 border rounded bg-transparent w-24"
            />
          </div>
        </header>

        <div className="flex-1 overflow-hidden relative">
          {isActivelyLoadingHistory ? (
            <div className="absolute inset-0 flex items-center justify-center bg-white/50 dark:bg-black/50 backdrop-blur-sm z-20">
              <span className="animate-pulse">Loading history...</span>
            </div>
          ) : (
            <ChatInterface 
              user={{ id: userId, name: userName }} 
              threadId={threadId} 
              promptVersion={promptVersion}
              initialMessages={initialMessages}
              onNewThreadId={handleNewThreadId}
            />
          )}
        </div>
      </main>

      {showDocumentManager && (
        <DocumentManager 
          userId={userId} 
          onClose={() => setShowDocumentManager(false)} 
        />
      )}
    </div>
  );
}

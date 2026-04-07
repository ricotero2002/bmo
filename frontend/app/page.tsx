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
import Profile from "@/components/Profile";
import { testSecureEndpoint } from "@/services/api";

export default function Home() {
  // Check if user is authenticated

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
  const [showProfile, setShowProfile] = useState(false);

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

  const handleTestSecure = async () => {
    try {
      const res = await testSecureEndpoint();
      alert(JSON.stringify(res, null, 2));
    } catch (e: any) {
      alert("Error probando endpoint seguro: " + e.message);
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
        <Profile />
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
            <button
              onClick={() => setShowProfile(true)}
              className="px-3 py-1 bg-zinc-200 dark:bg-zinc-800 hover:bg-zinc-300 dark:hover:bg-zinc-700 text-zinc-900 dark:text-zinc-100 rounded mx-1 transition"
            >
              Perfil
            </button>
            <button
              onClick={handleTestSecure}
              className="px-3 py-1 bg-blue-100 hover:bg-blue-200 text-blue-800 rounded mx-1 transition"
            >
              Test Backend
            </button>
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

      {showProfile && !showLogin && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in duration-200">
          <div className="bg-white dark:bg-zinc-950 p-6 rounded-lg w-full max-w-md relative">
            <button
              onClick={() => setShowProfile(false)}
              className="absolute top-4 right-4 text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
            >
              x
            </button>
            <Profile />
          </div>
        </div>
      )}
    </div>
  );
}

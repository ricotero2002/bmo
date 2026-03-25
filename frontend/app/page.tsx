"use client";

import ChatInterface from "@/components/ChatInterface";
import { useState } from "react";

export default function Home() {
  const [userId, setUserId] = useState("Agustin");
  const [userName, setUserName] = useState("Agustin");
  const [threadId, setThreadId] = useState("test-thread");
  const [promptVersion, setPromptVersion] = useState("rag_v2");

  return (
    <div className="flex flex-col min-h-screen bg-zinc-50 dark:bg-black p-4 h-screen">
      <main className="flex-1 w-full max-w-4xl mx-auto flex flex-col items-center overflow-hidden">
        <h1 className="text-3xl font-semibold text-center mb-4 text-black dark:text-zinc-50 flex-none shrink-0 pt-4">
          Personal AI Assistant
        </h1>

        <div className="w-full max-w-3xl mb-4 grid grid-cols-2 lg:grid-cols-4 gap-4 p-4 border rounded-lg bg-white dark:bg-zinc-900 border-zinc-200 dark:border-zinc-800 flex-none shrink-0">
          <div className="flex flex-col">
            <label className="text-xs font-bold mb-1 text-zinc-500">User ID</label>
            <input 
              value={userId} 
              onChange={(e) => setUserId(e.target.value)} 
              className="p-1 border rounded text-sm bg-transparent text-foreground"
            />
          </div>
          <div className="flex flex-col">
            <label className="text-xs font-bold mb-1 text-zinc-500">User Name</label>
            <input 
              value={userName} 
              onChange={(e) => setUserName(e.target.value)} 
              className="p-1 border rounded text-sm bg-transparent text-foreground"
            />
          </div>
          <div className="flex flex-col">
            <label className="text-xs font-bold mb-1 text-zinc-500">Thread ID</label>
            <input 
              value={threadId} 
              onChange={(e) => setThreadId(e.target.value)} 
              className="p-1 border rounded text-sm bg-transparent text-foreground"
            />
          </div>
          <div className="flex flex-col">
            <label className="text-xs font-bold mb-1 text-zinc-500">Prompt Version</label>
            <input 
              value={promptVersion} 
              onChange={(e) => setPromptVersion(e.target.value)} 
              className="p-1 border rounded text-sm bg-transparent text-foreground"
            />
          </div>
        </div>

        <div className="w-full max-w-3xl flex-1 flex flex-col min-h-0">
            <ChatInterface 
                user={{ id: userId, name: userName }} 
                threadId={threadId} 
                promptVersion={promptVersion} 
            />
        </div>
      </main>
    </div>
  );
}

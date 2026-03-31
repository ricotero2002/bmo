"use client";

import React from "react";
import { useQuery } from "@tanstack/react-query";
import { MessageSquare, PlusCircle, Loader2, Database } from "lucide-react";
import { useUser } from "@/app/context/UserContext";
import { fetchChats, Chat } from "@/services/api";

interface SidebarProps {
  currentThreadId: string;
  onSelectChat: (threadId: string) => void;
  onNewChat: () => void;
  onManageDocuments: () => void;
}

export default function Sidebar({ currentThreadId, onSelectChat, onNewChat, onManageDocuments }: SidebarProps) {
  const { userId } = useUser();

  const { data: chats, isLoading, isError } = useQuery<Chat[]>({
    queryKey: ["chats", userId],
    queryFn: () => fetchChats(userId),
    enabled: !!userId, // Solo ejecutar si hay userId
  });

  return (
    <div className="w-64 h-full bg-zinc-50 dark:bg-zinc-950 border-r border-zinc-200 dark:border-zinc-800 flex flex-col hide-scrollbar overflow-y-auto">
      <div className="p-4 border-b border-zinc-200 dark:border-zinc-800 sticky top-0 bg-zinc-50 dark:bg-zinc-950 z-10">
        <button
          onClick={onNewChat}
          className="w-full flex items-center justify-center gap-2 bg-black dark:bg-white text-white dark:text-black py-2 px-4 rounded-md font-medium hover:bg-zinc-800 dark:hover:bg-zinc-200 transition-colors"
        >
          <PlusCircle size={18} />
          <span>New Chat</span>
        </button>
      </div>

      <div className="flex-1 p-2 space-y-1 overflow-y-auto">
        {isLoading && (
          <div className="flex justify-center p-4">
            <Loader2 className="animate-spin text-zinc-400" size={24} />
          </div>
        )}

        {isError && (
          <div className="text-center p-4 text-xs text-red-500">
            Failed to load chats.
          </div>
        )}

        {chats?.map((chat) => (
          <button
            key={chat.thread_id}
            onClick={() => onSelectChat(chat.thread_id)}
            className={`w-full text-left px-3 py-2 rounded-md text-sm transition-colors flex items-center gap-3 truncate ${
              currentThreadId === chat.thread_id
                ? "bg-zinc-200 dark:bg-zinc-800 font-medium"
                : "hover:bg-zinc-100 dark:hover:bg-zinc-900 text-zinc-600 dark:text-zinc-400"
            }`}
          >
            <MessageSquare size={16} className="shrink-0" />
            <span className="truncate">{chat.title || "New Conversation"}</span>
          </button>
        ))}

        {!isLoading && !isError && chats?.length === 0 && (
          <div className="text-center p-4 text-xs text-zinc-500">
            No active chats. Start a new one!
          </div>
        )}
      </div>
      
      <div className="p-4 border-t border-zinc-200 dark:border-zinc-800 flex flex-col gap-3">
        <button
          onClick={onManageDocuments}
          className="w-full flex items-center justify-center gap-2 bg-zinc-100 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 py-2 px-4 rounded-md text-sm font-medium hover:bg-zinc-200 dark:hover:bg-zinc-800 transition-colors"
        >
          <Database size={16} />
          <span>Manage Documents</span>
        </button>
        <div className="text-xs text-zinc-500 flex items-center gap-3">
          <img src="/avatar.png" alt="Assistant" className="w-8 h-8 rounded-full bg-white border border-zinc-200 dark:border-zinc-800 object-cover" />
          <span className="truncate">Logged as: {userId || "Anonymous"}</span>
        </div>
      </div>
    </div>
  );
}

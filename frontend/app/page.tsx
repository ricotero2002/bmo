import ChatInterface from "@/components/ChatInterface";

export default function Home() {
  return (
    <div className="flex flex-col min-h-screen bg-zinc-50 dark:bg-black p-4">
      <main className="flex-1 w-full max-w-4xl mx-auto flex flex-col justify-center">
        <h1 className="text-3xl font-semibold text-center mb-8 text-black dark:text-zinc-50">
          Personal AI Assistant
        </h1>
        <ChatInterface />
      </main>
    </div>
  );
}

1. La "Lista de Compras" de UI (shadcn/ui + Tailwind)
El estándar actual para interfaces de IA minimalistas y profesionales es la combinación de Tailwind CSS y shadcn/ui. Para armar el chat, abre tu terminal en Next.js e instala estos componentes exactos:

Bash
npx shadcn-ui@latest add input button avatar scroll-area card

Con esto, construiremos dos elementos visuales clave:

Chat Bubble: Contenedores diferenciados visualmente para el usuario y el asistente.

Prompt Input: La barra inferior donde el usuario escribe, con su botón de enviar.

2. El Intermediario (Next.js API Route)
Next.js actuará como un puente seguro. Recibe el mensaje de tu frontend, le adjunta tu token de seguridad (JWT o cookie) y le pide el streaming a FastAPI.

Crea el archivo src/app/api/chat/route.ts:

TypeScript
// src/app/api/chat/route.ts
import { cookies } from 'next/headers';

export async function POST(req: Request) {
  // 1. Extraemos los mensajes enviados por useChat
  const { messages } = await req.json();

  // 2. Validaciones de Seguridad: Obtenemos el token de sesión
  const token = cookies().get('session_token')?.value;

  if (!token) {
    return new Response('Unauthorized', { status: 401 });
  }

  // 3. Llamamos a tu backend en FastAPI
  const response = await fetch('http://tu-backend-fastapi.com/api/v1/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}` // Pasamos la autenticación
    },
    body: JSON.stringify({ messages }),
  });

  // 4. Devolvemos el streaming directamente al frontend de Next.js
  // Vercel AI SDK es lo suficientemente inteligente para procesar este stream de texto
  return new Response(response.body, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
    },
  });
}

tengo que acomodar el tema del link

3. La Interfaz de Usuario (El Componente de Chat)
Aquí es donde ocurre la magia visual. Gracias al hook useChat, no tienes que crear useState manuales para el input o el historial; el SDK lo hace por ti.

Crea el archivo src/components/ChatInterface.tsx:

TypeScript
'use client';

import { useChat } from 'ai/react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { SendIcon, UserIcon, BotIcon } from 'lucide-react';

export default function ChatInterface() {
  // useChat llama por defecto a /api/chat y maneja el array de mensajes en vivo
  const { messages, input, handleInputChange, handleSubmit, isLoading } = useChat();

  return (
    <div className="flex flex-col h-[600px] w-full max-w-2xl mx-auto border rounded-lg shadow-sm bg-background">
      
      {/* Área de Mensajes (Historial en vivo) */}
      <ScrollArea className="flex-1 p-4">
        <div className="flex flex-col gap-4">
          {messages.map((m) => (
            <div
              key={m.id}
              className={`flex gap-3 text-sm ${
                m.role === 'user' ? 'flex-row-reverse' : 'flex-row'
              }`}
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
                className={`p-3 rounded-lg max-w-[80%] ${
                  m.role === 'user'
                    ? 'bg-primary text-primary-foreground rounded-tr-none'
                    : 'bg-muted text-foreground rounded-tl-none'
                }`}
              >
                {m.content}
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>

      {/* Barra de Input */}
      <div className="p-4 border-t bg-background">
        <form
          onSubmit={handleSubmit}
          className="flex w-full items-center space-x-2"
        >
          <Input
            value={input}
            onChange={handleInputChange}
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
¿Qué hace FastAPI del otro lado?
Para que esto funcione, tu endpoint de FastAPI (/api/v1/chat/stream) simplemente debe recibir el array de mensajes y usar un StreamingResponse de Starlette/FastAPI para ir devolviendo los fragmentos de texto (chunks) a medida que Gemini los genera.
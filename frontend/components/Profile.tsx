"use client";

import { useEffect, useState } from "react";
import { useUser } from "@/app/context/UserContext";

export default function Profile() {
  const { userId, setUserId, userName, setUserName } = useUser();
  const [auth0User, setAuth0User] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [tempId, setTempId] = useState("");

  // Al montar, verificamos si hay una sesión real de Auth0
  useEffect(() => {
    async function checkAuth0Session() {
      try {
        const res = await fetch("/auth/profile"); // Ajustado para el SDK de Auth0 Next.js (por defecto suele ser /api/auth/me)
        if (res.ok) {
          const data = await res.json();
          setAuth0User(data);
          // Sincronizamos el UserContext de la app con el ID real de Auth0
          setUserId(data.sub); // Auth0 usa 'sub' como ID de usuario único
          setUserName(data.name || data.nickname || data.email);
        }
      } catch (error) {
        console.error("No Auth0 session found");
      } finally {
        setIsLoading(false);
      }
    }
    checkAuth0Session();
  }, [setUserId, setUserName]);

  // Manejo de login manual temporal (para desarrollo)
  const handleManualLogin = (e: React.FormEvent) => {
    e.preventDefault();
    if (tempId.trim()) {
      setUserId(tempId.trim());
      setUserName(tempId.trim());
    }
  };

  if (isLoading) return <div className="p-4 text-sm flex items-center justify-center min-h-screen">Cargando perfil...</div>;

  return (
    <div className="bg-white dark:bg-zinc-900 p-6 rounded-lg shadow-sm border border-zinc-200 dark:border-zinc-800 max-w-sm w-full mx-auto mt-10">
      <div className="text-center mb-6">
        {auth0User?.picture ? (
          <img src={auth0User.picture} alt="Profile" className="w-16 h-16 rounded-full mx-auto mb-4 border" />
        ) : (
          <img src="/avatar.png" alt="Assistant" className="w-16 h-16 rounded-full mx-auto mb-4 border" />
        )}
        <h1 className="text-2xl font-semibold">{auth0User ? "Perfil Auth0" : "Modo Desarrollo"}</h1>
      </div>

      {auth0User ? (
        <div className="flex flex-col gap-4 text-sm">
          <p><strong>Nombre:</strong> {auth0User.name}</p>
          <p><strong>Email:</strong> {auth0User.email}</p>
          <p className="text-xs text-zinc-500 truncate"><strong>ID:</strong> {auth0User.sub}</p>
          <a href="/auth/logout" className="bg-red-500 hover:bg-red-600 text-white py-2 rounded-md font-medium text-center transition">
            Cerrar Sesión Auth0
          </a>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <p className="text-sm text-zinc-500 mb-2">Ingresa con Auth0 (Recomendado) o usa un ID local.</p>

          <a href="/auth/login?screen_hint=signup" className="bg-blue-600 hover:bg-blue-700 text-white py-2 rounded-md font-medium text-center transition">
            Crear Cuenta Auth0
          </a>
          <a href="/auth/login" className="bg-black dark:bg-white text-white dark:text-black py-2 rounded-md font-medium text-center transition">
            Iniciar Sesión Auth0
          </a>

          <div className="relative flex py-2 items-center">
            <div className="flex-grow border-t border-zinc-300 dark:border-zinc-700"></div>
            <span className="flex-shrink-0 mx-4 text-zinc-400 text-xs">O MODO LOCAL</span>
            <div className="flex-grow border-t border-zinc-300 dark:border-zinc-700"></div>
          </div>

          <form onSubmit={handleManualLogin} className="flex flex-col gap-2">
            <input
              value={tempId}
              onChange={(e) => setTempId(e.target.value)}
              placeholder="ID manual (ej: agustin)"
              className="p-2 border rounded-md bg-transparent text-sm"
              autoFocus
            />
            <button type="submit" className="bg-zinc-200 dark:bg-zinc-800 text-zinc-900 dark:text-white py-2 rounded-md font-medium text-sm hover:opacity-80">
              Forzar ID Local
            </button>
          </form>
        </div>
      )}
    </div>
  );
}

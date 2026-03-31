"use client";

import React, { createContext, useContext, useState, ReactNode } from "react";

interface UserContextType {
  userId: string;
  setUserId: (id: string) => void;
  userName: string;
  setUserName: (name: string) => void;
}

const UserContext = createContext<UserContextType | undefined>(undefined);

export function UserProvider({ children }: { children: ReactNode }) {
  // Defaulting to "Agustin" as the initial state based on previous page.tsx
  const [userId, setUserId] = useState("agustin");
  const [userName, setUserName] = useState("agustin");

  return (
    <UserContext.Provider value={{ userId, setUserId, userName, setUserName }}>
      {children}
    </UserContext.Provider>
  );
}

export function useUser() {
  const context = useContext(UserContext);
  if (context === undefined) {
    throw new Error("useUser must be used within a UserProvider");
  }
  return context;
}

//Create an Auth0 client instance for server-side session management. This file initializes the SDK with your Auth0 credentials.


import { Auth0Client } from "@auth0/nextjs-auth0/server";

export const auth0 = new Auth0Client({
    authorizationParameters: {
        // 1. EL AUDIENCE: Esto le dice a Auth0 "Dame un JWT real para FastAPI, no un token opaco"
        // Reemplaza esto por el 'Identifier' exacto que le pusiste a tu API en Auth0
        audience: process.env.AUTH0_AUDIENCE || "https://bmo-api.tusitio.com",

        // 2. LOS SCOPES: Qué información quieres pedir
        // 'offline_access' es vital para que Auth0 te entregue el Refresh Token
        scope: "openid profile email offline_access"
    }
});
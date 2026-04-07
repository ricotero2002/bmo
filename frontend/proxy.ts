//Configure the authentication proxy to intercept requests and handle the OAuth flow.

/*
The proxy layer automatically mounts these authentication routes:

/auth/login - Redirects to Auth0 login page
/auth/logout - Logs out the user
/auth/callback - Handles the OAuth callback
/auth/profile - Returns the user profile as JSON
/auth/access-token - Returns the access token
/auth/backchannel-logout - Receives a logout_token when a configured Back-Channel Logout initiator occurs
*/

import { auth0 } from "./lib/auth0";

export async function proxy(request: Request) {
    const authResponse = await auth0.middleware(request);

    // Always return the auth response.
    //
    // Note: The auth response forwards requests to your app routes by default.
    // If you need to block requests, do it before calling auth0.middleware() or
    // copy the authResponse headers except for x-middleware-next to your blocking response.
    return authResponse;
}

export const config = {
    matcher: [
        "/((?!_next/static|_next/image|favicon.ico|sitemap.xml|robots.txt).*)",
    ],
};

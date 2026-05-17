#!/usr/bin/env python3
"""
Gmail OAuth2 setup script.

Run this once to obtain a refresh token for Gmail read-only access.
The refresh token is printed at the end and should be saved to .env.local

Usage:
    python -m app.gmail_auth

Prerequisites:
    1. Create a Google Cloud project: https://console.cloud.google.com/
    2. Enable the Gmail API
    3. Create OAuth2 credentials (Desktop application type)
    4. Copy Client ID and Client Secret
    5. Set them in your environment or edit this script
"""

from __future__ import annotations

import http.server
import socketserver
import urllib.parse
import webbrowser
from typing import Any

import httpx

# OAuth2 configuration
# These can be set here or passed via environment variables
CLIENT_ID = ""
CLIENT_SECRET = ""
REDIRECT_URI = "http://localhost:8080/callback"
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Global to store the authorization code
_auth_code: str | None = None


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for OAuth callback."""

    def do_GET(self) -> None:
        global _auth_code

        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            _auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"""
                <html>
                <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                    <h1>Authorization Successful!</h1>
                    <p>You can close this window and return to the terminal.</p>
                </body>
                </html>
                """
            )
        elif "error" in params:
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            error = params["error"][0]
            self.wfile.write(
                f"""
                <html>
                <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                    <h1>Authorization Failed</h1>
                    <p>Error: {error}</p>
                </body>
                </html>
                """.encode()
            )
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress HTTP server logs
        pass


def get_authorization_url(client_id: str) -> str:
    """Build the Google OAuth2 authorization URL."""
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "response_type": "code",
        # Prompt ensures we get a refresh token even if previously authorized
        "prompt": "consent",
    }
    query = urllib.parse.urlencode(params)
    return f"https://accounts.google.com/o/oauth2/v2/auth?{query}"


async def exchange_code_for_token(
    client_id: str, client_secret: str, code: str
) -> dict[str, Any]:
    """Exchange authorization code for access and refresh tokens."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": REDIRECT_URI,
            },
        )
        resp.raise_for_status()
        return resp.json()


def run_callback_server() -> str:
    """Run the callback server and return the authorization code."""
    global _auth_code
    _auth_code = None

    with socketserver.TCPServer(("", 8080), OAuthCallbackHandler) as httpd:
        httpd.timeout = 120  # 2 minute timeout
        while _auth_code is None:
            httpd.handle_request()

    if _auth_code is None:
        raise RuntimeError("Did not receive authorization code")

    return _auth_code


async def main() -> None:
    """Main OAuth flow."""
    import os

    client_id = CLIENT_ID or os.environ.get("GMAIL_CLIENT_ID", "")
    client_secret = CLIENT_SECRET or os.environ.get("GMAIL_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        print("Error: CLIENT_ID and CLIENT_SECRET must be set.")
        print("\nTo get these:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create or select a project")
        print("3. Enable the Gmail API")
        print("4. Go to APIs & Services > Credentials")
        print("5. Click 'Create Credentials' > 'OAuth client ID'")
        print("6. Choose 'Desktop app' as the application type")
        print("7. Copy the Client ID and Client Secret")
        print("\nThen either:")
        print("  - Edit app/gmail_auth.py and set CLIENT_ID and CLIENT_SECRET")
        print("  - Or set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET environment variables")
        return

    # Build authorization URL
    auth_url = get_authorization_url(client_id)

    print("=" * 60)
    print("Gmail OAuth2 Setup")
    print("=" * 60)
    print("\nA browser window will open for authorization.")
    print("Please log in with the Google account you want to access.\n")

    # Open browser
    webbrowser.open(auth_url)
    print(f"If the browser doesn't open, visit:\n{auth_url}\n")

    # Wait for callback
    print("Waiting for authorization...")
    code = run_callback_server()
    print("Authorization received!\n")

    # Exchange code for tokens
    print("Exchanging code for tokens...")
    try:
        tokens = await exchange_code_for_token(client_id, client_secret, code)
    except httpx.HTTPError as exc:
        print(f"Error exchanging code: {exc}")
        return

    # Display results
    print("\n" + "=" * 60)
    print("SUCCESS! Add these to your .env.local file:")
    print("=" * 60)
    print(f"\nGMAIL_CLIENT_ID={client_id}")
    print(f"GMAIL_CLIENT_SECRET={client_secret}")
    print(f"GMAIL_REFRESH_TOKEN={tokens.get('refresh_token', 'N/A')}")
    print("\n# Optional: comma-separated list of important sender emails")
    print("# GMAIL_SENDER_EMAILS=person@example.com,alerts@example.com")
    print("\n" + "=" * 60)

    if "refresh_token" not in tokens:
        print("\nWARNING: No refresh token received!")
        print("This usually means you've authorized this app before.")
        print("To force a new refresh token:")
        print("1. Go to https://myaccount.google.com/permissions")
        print("2. Find and remove this app")
        print("3. Run this script again")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())

import os
import sys
import re
import random
import asyncio
import httpx
from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse

# -----------------------------------------------------------------------------
# Startup configuration & Fail-Fast check
# -----------------------------------------------------------------------------
MCP_API_KEY = os.environ.get("MCP_API_KEY")
if not MCP_API_KEY:
    print(
        "CRITICAL ERROR: Environment variable 'MCP_API_KEY' is not set.\n"
        "Please configure 'MCP_API_KEY' and restart the server.",
        file=sys.stderr
    )
    sys.exit(1)

# -----------------------------------------------------------------------------
# ASGI Bearer Authentication Middleware
# -----------------------------------------------------------------------------
class BearerAuthASGIMiddleware:
    """
    Standard ASGI middleware that checks for 'Authorization: Bearer <key>'
    on all incoming paths starting with '/mcp'.
    Ensures safe handling of Starlette chunked/streaming SSE responses.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            if path.startswith("/mcp"):
                headers = dict(scope.get("headers", []))
                auth_bytes = headers.get(b"authorization")
                if not auth_bytes:
                    await self._send_401(send, "Missing Authorization header")
                    return
                
                try:
                    auth_str = auth_bytes.decode("utf-8")
                except Exception:
                    await self._send_401(send, "Invalid headers encoding")
                    return
                
                parts = auth_str.split()
                if len(parts) != 2 or parts[0].lower() != "bearer":
                    await self._send_401(
                        send, 
                        "Invalid Authorization header format. Expected 'Bearer <key>'"
                    )
                    return
                
                if parts[1] != MCP_API_KEY:
                    await self._send_401(send, "Invalid API key")
                    return
        
        await self.app(scope, receive, send)

    async def _send_401(self, send, detail):
        response_body = f'{{"detail":"{detail}"}}'.encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(response_body)).encode("ascii")),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": response_body,
        })

# -----------------------------------------------------------------------------
# Initialize FastMCP Server & Tools
# -----------------------------------------------------------------------------
mcp = FastMCP(
    "Telephone Translator",
    instructions="A spec-compliant Remote MCP server for translations and text formatting."
)

LANGUAGES = [
    'es', 'fr', 'de', 'it', 'ja', 'ko', 'zh-CN', 'ru', 'pt', 'ar', 
    'tr', 'nl', 'pl', 'fi', 'el', 'sv', 'hi', 'da', 'no', 'vi', 'he'
]

SPELLING_MAP = {
    "teh": "the",
    "recieve": "receive",
    "occured": "occurred",
    "seperete": "separate",
    "definately": "definitely",
    "acheive": "achieve",
    "untill": "until",
    "begining": "beginning",
    "wierd": "weird"
}

# -----------------------------------------------------------------------------
# Tool Helper Logic
# -----------------------------------------------------------------------------
async def translate_once(client: httpx.AsyncClient, text: str, from_lang: str, to_lang: str) -> str:
    url = "https://translate.googleapis.com/translate_a/single"
    params = {
        "client": "gtx",
        "sl": from_lang,
        "tl": to_lang,
        "dt": "t",
        "q": text
    }
    
    try:
        response = await client.get(
            url, 
            params=params, 
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            },
            timeout=10.0
        )
        if response.status_code != 200:
            return text
            
        res_data = response.json()
        translated_text = ""
        if res_data and isinstance(res_data, list) and len(res_data) > 0 and isinstance(res_data[0], list):
            for part in res_data[0]:
                if isinstance(part, list) and len(part) > 0 and isinstance(part[0], str):
                    translated_text += part[0]
        return translated_text if translated_text else text
    except Exception:
        return text

async def telephone_translate_helper(text: str, rounds: int, return_language: str, preserve_quotes: bool) -> str:
    quotes = []
    
    if preserve_quotes:
        def replace_quote(match):
            quotes.append(match.group(0))
            return f"__QUOTE_{len(quotes)-1}__"
        placeholder_text = re.sub(r'"([^"]*)"', replace_quote, text)
    else:
        placeholder_text = text
        
    current_text = placeholder_text
    current_lang = "auto"
    
    async with httpx.AsyncClient() as client:
        # Perform rounds - 1 intermediate translations
        for i in range(rounds - 1):
            choices = [l for l in LANGUAGES if l != current_lang and l != return_language]
            if not choices:
                choices = LANGUAGES
            next_lang = random.choice(choices)
            
            current_text = await translate_once(client, current_text, current_lang, next_lang)
            current_lang = next_lang
            await asyncio.sleep(0.05) # Polite delay
            
        # Final round back to return_language
        current_text = await translate_once(client, current_text, current_lang, return_language)
        
    # Restore quotes if applicable
    if preserve_quotes and quotes:
        restore_pattern = re.compile(r'__\s*QUOTE\s*_\s*(\d+)\s*__', re.IGNORECASE)
        def restore_quote(match):
            idx = int(match.group(1))
            if idx < len(quotes):
                return quotes[idx]
            return match.group(0)
        current_text = restore_pattern.sub(restore_quote, current_text)
        
    return current_text

def format_text_helper(
    text: str,
    remove_double_spaces: bool,
    straighten_quotes: bool,
    indent_paragraphs: bool,
    fix_spelling: bool
) -> str:
    # 1. Remove double spaces
    if remove_double_spaces:
        text = re.sub(r' {2,}', ' ', text)
        
    # 2. Convert curly quotes & backticks
    if straighten_quotes:
        text = text.replace("“", '"').replace("”", '"')
        text = text.replace("‘", "'").replace("’", "'").replace("`", "'")
        
    # 3. Fix common spelling errors
    if fix_spelling:
        for wrong, right in SPELLING_MAP.items():
            pattern = re.compile(rf'\b{wrong}\b', re.IGNORECASE)
            def replace(match):
                word = match.group(0)
                if word.isupper():
                    return right.upper()
                elif word[0].isupper():
                    return right.capitalize()
                return right
            text = pattern.sub(replace, text)
            
    # 4. Indent paragraphs (done last so spacing is not collapsed by remove_double_spaces)
    if indent_paragraphs:
        lines = text.split('\n')
        formatted_lines = []
        for idx, line in enumerate(lines):
            if idx == 0 and line.strip():
                formatted_lines.append("    " + line)
            elif idx > 0 and line.strip() and not lines[idx-1].strip():
                formatted_lines.append("    " + line)
            else:
                formatted_lines.append(line)
        text = '\n'.join(formatted_lines)
        
    return text

# -----------------------------------------------------------------------------
# Exposing MCP Tools
# -----------------------------------------------------------------------------
@mcp.tool()
async def telephone_translate(
    text: str,
    rounds: int = 8,
    return_language: str = "en",
    preserve_quotes: bool = True
) -> str:
    """
    Send text through multiple random translation steps to deliberately distort/mangle it before returning the final translation.

    Args:
        text: The text to translate.
        rounds: Number of translation rounds (default: 8, clamp 5..50).
        return_language: Final target language (default: en).
        preserve_quotes: Whether to preserve double-quoted text using placeholders.
    """
    clamped_rounds = max(5, min(50, rounds))
    return await telephone_translate_helper(
        text=text,
        rounds=clamped_rounds,
        return_language=return_language,
        preserve_quotes=preserve_quotes
    )

@mcp.tool()
def format_text(
    text: str,
    remove_double_spaces: bool = True,
    straighten_quotes: bool = False,
    indent_paragraphs: bool = False,
    fix_spelling: bool = False
) -> str:
    """
    Format text by removing extra spaces, converting quotes, indenting paragraphs, and fixing common spelling mistakes.

    Args:
        text: The text to format.
        remove_double_spaces: Remove extra spaces.
        straighten_quotes: Convert curly quotes to straight quotes.
        indent_paragraphs: Indent paragraphs with 4 spaces.
        fix_spelling: Fix common spelling errors.
    """
    return format_text_helper(
        text=text,
        remove_double_spaces=remove_double_spaces,
        straighten_quotes=straighten_quotes,
        indent_paragraphs=indent_paragraphs,
        fix_spelling=fix_spelling
    )

# -----------------------------------------------------------------------------
# Streamable HTTP App Exposure & Health Check Route
# -----------------------------------------------------------------------------
# Create the official Streamable HTTP Starlette ASGI application
base_app = mcp.streamable_http_app()

# Register health check route at root / on the base application
async def health(request):
    return JSONResponse({
        "status": "healthy",
        "service": "Telephone Translator Remote MCP Server",
        "version": "1.0.0"
    })

base_app.add_route("/", health, methods=["GET"])

# Wrap with our custom security middleware to protect all /mcp endpoints
app = BearerAuthASGIMiddleware(base_app)

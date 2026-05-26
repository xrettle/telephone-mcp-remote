import os
import sys
import re
import random
import asyncio
import httpx
from fastapi import FastAPI, Request, HTTPException, status

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

# Initialize FastAPI App
app = FastAPI(
    title="Telephone Translator Remote MCP Server",
    description="A minimal Python remote Model Context Protocol (MCP) server.",
    version="1.0.0"
)

# Supported translation languages for the telephone_translate tool
LANGUAGES = [
    'es', 'fr', 'de', 'it', 'ja', 'ko', 'zh-CN', 'ru', 'pt', 'ar', 
    'tr', 'nl', 'pl', 'fi', 'el', 'sv', 'hi', 'da', 'no', 'vi', 'he'
]

# Spelling correction map for format_text
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
# Helper logic
# -----------------------------------------------------------------------------
async def verify_auth(auth_header: str):
    """
    Validates that the Authorization header matches the expected 'Bearer <token>'.
    Raises HTTP 401 on missing or incorrect auth.
    """
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header"
        )
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Expected 'Bearer <key>'"
        )
    if parts[1] != MCP_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )

async def translate_once(client: httpx.AsyncClient, text: str, from_lang: str, to_lang: str) -> str:
    """
    Translates a block of text using the lightweight Google Translate endpoint.
    """
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
        # Fallback gracefully to input text in case of API or network error
        return text

async def telephone_translate_helper(text: str, rounds: int, return_language: str, preserve_quotes: bool) -> str:
    """
    Translates text sequentially through multiple random languages and back to return_language.
    """
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
        # Perform rounds - 1 intermediate random translations
        for i in range(rounds - 1):
            choices = [l for l in LANGUAGES if l != current_lang and l != return_language]
            if not choices:
                choices = LANGUAGES
            next_lang = random.choice(choices)
            
            current_text = await translate_once(client, current_text, current_lang, next_lang)
            current_lang = next_lang
            await asyncio.sleep(0.05) # Polite delay
            
        # Final round to return language
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
    """
    Formats text by removing double spaces, converting quotes, indenting, and correcting spelling.
    """
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
            # Indent if first line of text or if preceded by an empty line
            if idx == 0 and line.strip():
                formatted_lines.append("    " + line)
            elif idx > 0 and line.strip() and not lines[idx-1].strip():
                formatted_lines.append("    " + line)
            else:
                formatted_lines.append(line)
        text = '\n'.join(formatted_lines)
        
    return text

# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------
@app.get("/")
async def health_check():
    """
    Unprotected health and status check endpoint.
    """
    return {
        "status": "healthy",
        "service": "Telephone Translator Remote MCP Server",
        "version": "1.0.0"
    }

@app.post("/mcp")
async def handle_mcp(request: Request):
    """
    Protected MCP endpoint. Uses Authorization: Bearer token auth.
    Supports tools/list and tools/call.
    """
    # Verify auth
    auth_header = request.headers.get("Authorization")
    await verify_auth(auth_header)
    
    # Parse JSON body
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )
    
    method = payload.get("method")
    req_id = payload.get("id")
    
    if not method:
        return {
            "jsonrpc": "2.0",
            "error": {
                "code": -32600,
                "message": "Invalid request: 'method' is required"
            },
            "id": req_id
        }
        
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "result": {
                "tools": [
                    {
                        "name": "telephone_translate",
                        "description": "Send text through multiple random translation steps to deliberately distort/mangle it before returning the final translation.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "text": {
                                    "type": "string",
                                    "description": "The text to translate"
                                },
                                "rounds": {
                                    "type": "integer",
                                    "description": "Number of translation rounds (default: 8, clamp 5..50)",
                                    "default": 8
                                },
                                "return_language": {
                                    "type": "string",
                                    "description": "Final target language (default: en)",
                                    "default": "en"
                                },
                                "preserve_quotes": {
                                    "type": "boolean",
                                    "description": "Whether to preserve double-quoted text using placeholders",
                                    "default": True
                                }
                            },
                            "required": ["text"]
                        }
                    },
                    {
                        "name": "format_text",
                        "description": "Format text by removing extra spaces, converting quotes, indenting paragraphs, and fixing common spelling mistakes.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "text": {
                                    "type": "string",
                                    "description": "The text to format"
                                },
                                "remove_double_spaces": {
                                    "type": "boolean",
                                    "description": "Whether to remove extra spaces (default: true)",
                                    "default": True
                                },
                                "straighten_quotes": {
                                    "type": "boolean",
                                    "description": "Whether to convert curly quotes to straight quotes (default: false)",
                                    "default": False
                                },
                                "indent_paragraphs": {
                                    "type": "boolean",
                                    "description": "Whether to indent paragraphs with 4 spaces (default: false)",
                                    "default": False
                                },
                                "fix_spelling": {
                                    "type": "boolean",
                                    "description": "Whether to fix common spelling mistakes (default: false)",
                                    "default": False
                                }
                            },
                            "required": ["text"]
                        }
                    }
                ]
            },
            "id": req_id
        }
        
    elif method == "tools/call":
        params = payload.get("params", {})
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if not tool_name:
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32602,
                    "message": "Invalid parameters: 'name' is required under 'params'"
                },
                "id": req_id
            }
            
        if tool_name == "telephone_translate":
            text = arguments.get("text")
            if text is None:
                return {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32602,
                        "message": "Invalid parameters: 'text' is required"
                    },
                    "id": req_id
                }
                
            rounds = arguments.get("rounds", 8)
            try:
                rounds = int(rounds)
            except (ValueError, TypeError):
                rounds = 8
            rounds = max(5, min(50, rounds))
            
            return_language = arguments.get("return_language", "en")
            preserve_quotes = arguments.get("preserve_quotes", True)
            if not isinstance(preserve_quotes, bool):
                preserve_quotes = True
                
            translated_res = await telephone_translate_helper(
                text=text,
                rounds=rounds,
                return_language=return_language,
                preserve_quotes=preserve_quotes
            )
            
            return {
                "jsonrpc": "2.0",
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": translated_res
                        }
                    ]
                },
                "id": req_id
            }
            
        elif tool_name == "format_text":
            text = arguments.get("text")
            if text is None:
                return {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32602,
                        "message": "Invalid parameters: 'text' is required"
                    },
                    "id": req_id
                }
                
            remove_double_spaces = arguments.get("remove_double_spaces", True)
            straighten_quotes = arguments.get("straighten_quotes", False)
            indent_paragraphs = arguments.get("indent_paragraphs", False)
            fix_spelling_opt = arguments.get("fix_spelling", False)
            
            # Coerce inputs to booleans if they aren't
            remove_double_spaces = remove_double_spaces if isinstance(remove_double_spaces, bool) else True
            straighten_quotes = straighten_quotes if isinstance(straighten_quotes, bool) else False
            indent_paragraphs = indent_paragraphs if isinstance(indent_paragraphs, bool) else False
            fix_spelling_opt = fix_spelling_opt if isinstance(fix_spelling_opt, bool) else False
            
            formatted_res = format_text_helper(
                text=text,
                remove_double_spaces=remove_double_spaces,
                straighten_quotes=straighten_quotes,
                indent_paragraphs=indent_paragraphs,
                fix_spelling=fix_spelling_opt
            )
            
            return {
                "jsonrpc": "2.0",
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": formatted_res
                        }
                    ]
                },
                "id": req_id
            }
            
        else:
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32601,
                    "message": f"Tool not found: {tool_name}"
                },
                "id": req_id
            }
            
    else:
        return {
            "jsonrpc": "2.0",
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}"
            },
            "id": req_id
        }

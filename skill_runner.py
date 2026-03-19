"""
skill_runner.py - Execute OpenJarvis skill TOML files using direct OpenRouter calls.
Replaces the broken Rust-dependent SkillExecutor for Windows.

Usage:
    uv run python skill_runner.py <skill-name> [key=value ...]

Examples:
    uv run python skill_runner.py web-summarize url=https://example.com
    uv run python skill_runner.py meeting-notes transcript_path=C:/notes.txt
    uv run python skill_runner.py email-draft context="need to reschedule" intent="politely decline" recipient="John"
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import httpx
import tomllib

SKILLS_DIR = Path.home() / ".openjarvis" / "skills"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
MODEL = "x-ai/grok-4.1-fast"
MAX_RESPONSE_BYTES = 1_048_576


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def tool_think(params: dict, context: dict) -> str:
    thought = params.get("thought", "")
    if not OPENROUTER_API_KEY:
        return "[Error: OPENROUTER_API_KEY not set]"
    try:
        resp = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": thought}],
            },
            timeout=60.0,
        )
        if not resp.is_success:
            return f"[OpenRouter error {resp.status_code}: {resp.text}]"
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[Error calling OpenRouter: {e}]"


def tool_http_request(params: dict, context: dict) -> str:
    url = params.get("url", "")
    method = params.get("method", "GET").upper()
    headers = params.get("headers") or {}
    body = params.get("body")
    timeout = params.get("timeout", 30)
    try:
        resp = httpx.request(
            method, url, headers=headers, content=body,
            timeout=float(timeout), follow_redirects=True,
        )
        text = resp.text
        if len(text) > MAX_RESPONSE_BYTES:
            text = text[:MAX_RESPONSE_BYTES] + "\n\n[Truncated]"
        return text
    except Exception as e:
        return f"[HTTP error: {e}]"


def tool_file_read(params: dict, context: dict) -> str:
    path = Path(params.get("path", ""))
    max_lines = params.get("max_lines")
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        if max_lines:
            text = "\n".join(text.splitlines()[:int(max_lines)])
        if len(text) > MAX_RESPONSE_BYTES:
            text = text[:MAX_RESPONSE_BYTES] + "\n\n[Truncated]"
        return text
    except Exception as e:
        return f"[File read error: {e}]"


def tool_pdf_extract(params: dict, context: dict) -> str:
    path = params.get("path", "")
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            text = "\n\n".join(page.extract_text() or "" for page in pdf.pages)
        return text[:MAX_RESPONSE_BYTES]
    except ImportError:
        try:
            import pypdf
            reader = pypdf.PdfReader(path)
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
            return text[:MAX_RESPONSE_BYTES]
        except ImportError:
            return "[Error: install pdfplumber — run: uv add pdfplumber]"
    except Exception as e:
        return f"[PDF extract error: {e}]"


def tool_web_search(params: dict, context: dict) -> str:
    query = params.get("query", "")
    max_results = params.get("max_results", 5)
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=int(max_results)))
        return json.dumps(results, indent=2)
    except ImportError:
        try:
            resp = httpx.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_redirect": "1"},
                timeout=15.0,
            )
            data = resp.json()
            abstract = data.get("AbstractText", "")
            related = [t.get("Text", "") for t in data.get("RelatedTopics", [])[:5]]
            return f"Abstract: {abstract}\n\nRelated: {chr(10).join(related)}"
        except Exception as e:
            return f"[Web search unavailable: {e}. Run: uv add duckduckgo-search]"


def tool_shell_exec(params: dict, context: dict) -> str:
    command = params.get("command", "")
    timeout = params.get("timeout", 30)
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True,
            text=True, timeout=float(timeout),
        )
        output = result.stdout + result.stderr
        return output[:MAX_RESPONSE_BYTES] if output else "[No output]"
    except subprocess.TimeoutExpired:
        return f"[Command timed out after {timeout}s]"
    except Exception as e:
        return f"[Shell exec error: {e}]"


def tool_memory_search(params: dict, context: dict) -> str:
    return "[No prior knowledge in memory store]"


def tool_memory_store(params: dict, context: dict) -> str:
    return "[Memory store not yet implemented]"


def tool_code_interpreter(params: dict, context: dict) -> str:
    code = params.get("code", "")
    lines = [l for l in code.splitlines() if not l.strip().startswith("#")]
    code = "\n".join(lines)
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=30,
        )
        return (result.stdout + result.stderr)[:MAX_RESPONSE_BYTES] or "[No output]"
    except Exception as e:
        return f"[Code interpreter error: {e}]"


TOOL_MAP = {
    "think": tool_think,
    "http_request": tool_http_request,
    "file_read": tool_file_read,
    "pdf_extract": tool_pdf_extract,
    "web_search": tool_web_search,
    "shell_exec": tool_shell_exec,
    "memory_search": tool_memory_search,
    "memory_store": tool_memory_store,
    "code_interpreter": tool_code_interpreter,
}


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------

def render_template(template: str, context: dict) -> str:
    """Replace {key} placeholders. JSON-escapes values that appear inside JSON strings."""
    def replacer(match):
        key = match.group(1)
        value = str(context.get(key, match.group(0)))
        # Check if placeholder is inside a JSON string (preceded by a quote)
        start = match.start()
        preceding = template[:start]
        in_json_string = preceding.count('"') % 2 == 1
        if in_json_string:
            # Escape for JSON string context
            return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        return value
    return re.sub(r"\{(\w+)\}", replacer, template)


# ---------------------------------------------------------------------------
# Skill runner
# ---------------------------------------------------------------------------

def run_skill(skill_name: str, inputs: dict) -> str:
    toml_path = SKILLS_DIR / f"{skill_name}.toml"
    if not toml_path.exists():
        return f"[Error: skill '{skill_name}' not found in {SKILLS_DIR}]"

    with open(toml_path, "rb") as f:
        data = tomllib.load(f)

    skill = data.get("skill", {})
    steps = skill.get("steps", [])
    context = dict(inputs)

    print(f"Running skill: {skill.get('name', skill_name)}", flush=True)
    print(f"Description: {skill.get('description', '')}", flush=True)
    print("-" * 40, flush=True)

    for i, step in enumerate(steps, 1):
        tool_name = step.get("tool_name", "")
        template = step.get("arguments_template", "{}")
        output_key = step.get("output_key", f"step_{i}")

        rendered = render_template(template, context)
        try:
            params = json.loads(rendered)
        except json.JSONDecodeError:
            params = {"input": rendered}

        tool_fn = TOOL_MAP.get(tool_name)
        if tool_fn is None:
            result = f"[Unknown tool: {tool_name}]"
        else:
            print(f"Step {i}/{len(steps)}: {tool_name} -> {output_key}", flush=True)
            result = tool_fn(params, context)

        context[output_key] = result

    if steps:
        last_key = steps[-1].get("output_key", f"step_{len(steps)}")
        return context.get(last_key, "[No output]")
    return "[No steps in skill]"


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        print(f"\nAvailable skills in {SKILLS_DIR}:")
        for f in sorted(SKILLS_DIR.glob("*.toml")):
            print(f"  {f.stem}")
        sys.exit(0)

    skill_name = sys.argv[1]
    inputs: dict = {}

    for arg in sys.argv[2:]:
        if "=" in arg:
            k, _, v = arg.partition("=")
            inputs[k.strip()] = v.strip()
        else:
            print(f"Warning: ignoring argument without '=': {arg}", file=sys.stderr)

    result = run_skill(skill_name, inputs)
    print("\n" + "=" * 40)
    print("RESULT:")
    print("=" * 40)
    print(result)


if __name__ == "__main__":
    main()

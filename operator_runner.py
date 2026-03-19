"""
operator_runner.py - Run OpenJarvis operators on Windows.
Replaces systemd/memory-backend dependencies with file-based memory and Task Scheduler.

Usage:
    uv run python operator_runner.py <operator_id>

Operators:
    news_digest      - Daily news digest (run at 8am via Task Scheduler)
    researcher       - Topic research monitor (run every 30min)
    system_monitor   - System health monitor (run every 5min)
    knowledge_curator - Knowledge graph builder (run every 2hr)
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import httpx

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL = "jarvis"
MODEL = "x-ai/grok-4.1-fast"
MEMORY_DIR = Path.home() / ".openjarvis" / "memory"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

OPERATORS_DIR = Path(__file__).parent / "src" / "openjarvis" / "operators" / "data"


# ---------------------------------------------------------------------------
# Memory (file-based)
# ---------------------------------------------------------------------------

def memory_store(key: str, value: str) -> None:
    safe_key = key.replace(":", "_").replace("/", "_")
    (MEMORY_DIR / f"{safe_key}.json").write_text(
        json.dumps({"key": key, "value": value, "updated": datetime.now().isoformat()}),
        encoding="utf-8",
    )


def memory_retrieve(key: str) -> str:
    safe_key = key.replace(":", "_").replace("/", "_")
    path = MEMORY_DIR / f"{safe_key}.json"
    if not path.exists():
        return ""
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("value", "")
    except Exception:
        return ""


def memory_search(query: str) -> str:
    results = []
    for f in sorted(MEMORY_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:20]:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if query.lower() in data.get("value", "").lower() or query.lower() in data.get("key", "").lower():
                results.append(f"{data['key']}: {data['value'][:200]}")
        except Exception:
            pass
    return "\n\n".join(results) if results else "[No matching memories]"


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def llm_call(system_prompt: str, user_message: str, temperature: float = 0.3) -> str:
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
                "temperature": temperature,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            },
            timeout=120.0,
        )
        if not resp.is_success:
            return f"[OpenRouter error {resp.status_code}: {resp.text}]"
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[LLM error: {e}]"


# ---------------------------------------------------------------------------
# Slack post
# ---------------------------------------------------------------------------

def post_to_slack(message: str, channel: str = SLACK_CHANNEL) -> bool:
    if not SLACK_BOT_TOKEN:
        print(f"[Slack not configured] {message}")
        return False
    try:
        resp = httpx.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
            json={"channel": channel, "text": message},
            timeout=15.0,
        )
        data = resp.json()
        return data.get("ok", False)
    except Exception as e:
        print(f"[Slack post error: {e}]")
        return False


# ---------------------------------------------------------------------------
# Web search
# ---------------------------------------------------------------------------

def web_search(query: str, max_results: int = 5) -> str:
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return json.dumps(results, indent=2)
    except Exception as e:
        return f"[Web search error: {e}]"


# ---------------------------------------------------------------------------
# System metrics
# ---------------------------------------------------------------------------

def get_system_metrics() -> dict:
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\")
        return {
            "cpu_percent": cpu,
            "ram_percent": ram.percent,
            "ram_used_gb": round(ram.used / 1e9, 1),
            "ram_total_gb": round(ram.total / 1e9, 1),
            "disk_percent": disk.percent,
            "disk_used_gb": round(disk.used / 1e9, 1),
            "disk_total_gb": round(disk.total / 1e9, 1),
        }
    except ImportError:
        return {"error": "psutil not installed"}


# ---------------------------------------------------------------------------
# Operator runners
# ---------------------------------------------------------------------------

def run_news_digest():
    print("Running: news_digest", flush=True)
    today = datetime.now().strftime("%Y-%m-%d")
    state = memory_retrieve("operator:news_digest:state")

    # Load operator system prompt
    toml_path = OPERATORS_DIR / "news_digest.toml"
    system_prompt = ""
    if toml_path.exists():
        import tomllib
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
        system_prompt = data.get("operator", {}).get("agent", {}).get("system_prompt", "")

    # Gather news on key topics
    topics = ["technology news", "AI artificial intelligence", "business news"]
    search_results = {}
    for topic in topics:
        print(f"  Searching: {topic}", flush=True)
        search_results[topic] = web_search(topic, max_results=3)

    context = f"""
Date: {today}
Previous state: {state or 'First run'}

Search results:
{json.dumps(search_results, indent=2)}
"""

    print("  Generating digest...", flush=True)
    digest = llm_call(
        system_prompt or "You are a news digest assistant. Create a concise daily news digest.",
        f"[OPERATOR TICK] Generate today's news digest based on this data:\n{context}",
        temperature=0.3,
    )

    memory_store(f"news_digest:{today}", digest)
    memory_store("operator:news_digest:state", json.dumps({
        "last_run": today, "topics_covered": topics,
    }))

    post_to_slack(f"*Daily News Digest — {today}*\n\n{digest}")
    print("  Done — posted to Slack", flush=True)


def run_researcher():
    print("Running: researcher", flush=True)
    now = datetime.now().isoformat()
    state_raw = memory_retrieve("operator:researcher:state")
    state = json.loads(state_raw) if state_raw else {}

    # Default topics — user can update by editing memory file
    topics_raw = memory_retrieve("researcher:topics")
    topics = json.loads(topics_raw) if topics_raw else ["AI agents", "Windows automation", "OpenJarvis"]

    toml_path = OPERATORS_DIR / "researcher.toml"
    system_prompt = ""
    if toml_path.exists():
        import tomllib
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
        system_prompt = data.get("operator", {}).get("agent", {}).get("system_prompt", "")

    findings = {}
    for topic in topics:
        print(f"  Researching: {topic}", flush=True)
        results = web_search(topic, max_results=3)
        prior = memory_retrieve(f"researcher:finding:{topic}:latest")
        findings[topic] = {"results": results, "prior": prior or "No prior findings"}

    context = f"""
Timestamp: {now}
Topics: {topics}
Previous state: {json.dumps(state)}

Findings:
{json.dumps(findings, indent=2)}
"""

    print("  Synthesizing...", flush=True)
    report = llm_call(
        system_prompt or "You are a research assistant. Summarize new findings and identify what is genuinely new.",
        f"[OPERATOR TICK] Analyze findings and report what is new:\n{context}",
        temperature=0.3,
    )

    for topic in topics:
        memory_store(f"researcher:finding:{topic}:latest", findings[topic]["results"])

    memory_store("operator:researcher:state", json.dumps({
        "last_run": now, "topics": topics,
    }))

    # Only post to Slack if there's something new
    if "[nothing new]" not in report.lower() and len(report) > 100:
        post_to_slack(f"*Research Update*\n\n{report}")
        print("  Posted to Slack", flush=True)
    else:
        print("  No significant new findings", flush=True)


def run_system_monitor():
    print("Running: system_monitor", flush=True)
    now = datetime.now().isoformat()
    metrics = get_system_metrics()
    state_raw = memory_retrieve("operator:system_monitor:state")
    state = json.loads(state_raw) if state_raw else {}

    print(f"  CPU: {metrics.get('cpu_percent')}%  RAM: {metrics.get('ram_percent')}%  Disk: {metrics.get('disk_percent')}%", flush=True)

    toml_path = OPERATORS_DIR / "system_monitor.toml"
    system_prompt = ""
    if toml_path.exists():
        import tomllib
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
        system_prompt = data.get("operator", {}).get("agent", {}).get("system_prompt", "")

    context = f"""
Timestamp: {now}
Current metrics: {json.dumps(metrics)}
Previous state: {json.dumps(state)}
Thresholds: CPU>85% warning, CPU>95% critical. RAM>80% warning, RAM>90% critical. Disk>85% warning, Disk>95% critical.
"""

    assessment = llm_call(
        system_prompt or "You are a system monitor. Assess system health and generate alerts only when thresholds are exceeded.",
        f"[OPERATOR TICK] Assess system health:\n{context}",
        temperature=0.2,
    )

    # Determine if alert needed
    cpu = metrics.get("cpu_percent", 0)
    ram = metrics.get("ram_percent", 0)
    disk = metrics.get("disk_percent", 0)
    alert_needed = cpu > 85 or ram > 80 or disk > 85

    memory_store("operator:system_monitor:state", json.dumps({
        "last_run": now,
        "last_metrics": metrics,
        "alert_needed": alert_needed,
    }))

    if alert_needed:
        post_to_slack(f"*System Alert*\nCPU: {cpu}% | RAM: {ram}% | Disk: {disk}%\n\n{assessment}")
        print("  Alert posted to Slack", flush=True)
    else:
        print("  System healthy — no alert", flush=True)


def run_knowledge_curator():
    print("Running: knowledge_curator", flush=True)
    now = datetime.now().isoformat()

    toml_path = OPERATORS_DIR / "knowledge_curator.toml"
    system_prompt = ""
    if toml_path.exists():
        import tomllib
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
        system_prompt = data.get("operator", {}).get("agent", {}).get("system_prompt", "")

    # Pull recent memories to curate
    recent = memory_search("researcher:finding")
    digest = memory_search("news_digest")

    context = f"""
Timestamp: {now}
Recent research findings:
{recent}

Recent news digests:
{digest[:2000] if digest else 'None'}
"""

    print("  Curating knowledge...", flush=True)
    summary = llm_call(
        system_prompt or "You are a knowledge curator. Extract key entities, concepts, and relationships from the provided memories and build a structured knowledge summary.",
        f"[OPERATOR TICK] Curate knowledge from recent memories:\n{context}",
        temperature=0.3,
    )

    knowledge_key = f"knowledge:curated:{datetime.now().strftime('%Y-%m-%d')}"
    memory_store(knowledge_key, summary)
    memory_store("operator:knowledge_curator:state", json.dumps({
        "last_run": now, "last_key": knowledge_key,
    }))

    print("  Knowledge curated and stored", flush=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

OPERATORS = {
    "news_digest": run_news_digest,
    "researcher": run_researcher,
    "system_monitor": run_system_monitor,
    "knowledge_curator": run_knowledge_curator,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        print("Available operators:", ", ".join(OPERATORS.keys()))
        sys.exit(0)

    op_id = sys.argv[1]
    if op_id not in OPERATORS:
        print(f"Unknown operator: {op_id}")
        print("Available:", ", ".join(OPERATORS.keys()))
        sys.exit(1)

    OPERATORS[op_id]()


if __name__ == "__main__":
    main()

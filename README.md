# OpenJarvis - Local Setup (Review Copy)

Running OpenJarvis locally on a Beelink mini PC (Windows 10, 8GB RAM) using OpenRouter for inference.

## Stack
- **OpenJarvis**: https://github.com/open-jarvis/OpenJarvis
- **Inference**: OpenRouter → `x-ai/grok-4.1-fast`
- **Python**: 3.12 via uv

## Setup

### Prerequisites
```cmd
winget install Python.Python.3.12
winget install OpenJS.NodeJS
winget install astral-sh.uv
```

### Install
```cmd
git clone https://github.com/open-jarvis/OpenJarvis.git C:\openjarvis
cd C:\openjarvis
uv sync --extra server
```

### Configure
1. Copy `config.toml.example` to `%USERPROFILE%\.openjarvis\config.toml`
2. Set your API key (never commit this):
```cmd
setx OPENROUTER_API_KEY "your-openrouter-key"
```

### Run
```cmd
cd C:\openjarvis
uv run jarvis serve --port 8000
```
Browser UI: http://localhost:5173

## Notes
- `OPENROUTER_API_KEY` is stored as a Windows user environment variable only — not in any file
- No local model/Ollama needed — all inference goes through OpenRouter

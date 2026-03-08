# DevOps Butler 🤖

AI-powered DevOps automation system that analyzes, plans, and deploys your applications automatically.

## Features

- 🔍 **Code Analysis**: Automatically detects your tech stack and dependencies
- 📋 **Smart Planning**: Creates deployment plans with cost estimates
- ⚡ **Auto Execution**: Deploys to AWS (ECS, EC2, Lambda, etc.)
- 🌐 **Browser Automation**: Handles AWS Console operations via AI
- 📊 **Monitoring**: Real-time deployment tracking and health checks

## Quick Start

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Copy environment file
cp .env.example .env
# Edit .env with your AWS credentials

# Run the server
python start.py

# Open browser
# http://localhost:8000
```

### Deploy to Cloud

See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for detailed instructions.

**Quick Deploy Options:**
- [Render](https://render.com) - Free tier, easiest setup
- [Railway](https://railway.app) - $5 free credit
- [Fly.io](https://fly.io) - Free tier with 3 VMs

## Usage

1. Open the web interface
2. Upload your code or provide a path
3. Add deployment instructions (optional)
4. Click "Deploy"
5. Approve the generated plan
6. Get your deployment URL!

## Architecture

```
┌─────────────┐
│   Web UI    │ ← FastAPI + WebSocket
└──────┬──────┘
       │
┌──────▼──────────────────────────┐
│      Orchestrator               │
│  (LangGraph State Machine)      │
└──────┬──────────────────────────┘
       │
   ┌───┴────┬────────┬──────────┬─────────┐
   │        │        │          │         │
┌──▼──┐ ┌──▼──┐ ┌───▼───┐ ┌────▼────┐ ┌──▼──┐
│Code │ │Plan │ │Execute│ │ Browser │ │Monitor│
│Analyzer│ │ner │ │  Agent│ │  Agent  │ │Agent│
└─────┘ └─────┘ └───────┘ └─────────┘ └─────┘
```

## Tech Stack

- **Backend**: Python, FastAPI, LangGraph
- **AI**: AWS Bedrock (Claude Sonnet, Nova)
- **Browser**: Playwright + Nova Act
- **Cloud**: AWS (ECS, EC2, Lambda, RDS, etc.)
- **Frontend**: Vanilla JS, WebSocket

## Environment Variables

See `.env` file for all configuration options. Key variables:

- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`: AWS credentials
- `AWS_BEARER_TOKEN_BEDROCK`: Bedrock API key
- `AWS_CONSOLE_EMAIL` / `AWS_CONSOLE_PASSWORD`: For browser automation
- `MONTHLY_BUDGET_USD`: Cost limit (default: $100)

## Security

⚠️ **Important**: Never commit your `.env` file. It contains sensitive credentials.

## License

MIT

## Support

For issues or questions, please open a GitHub issue.

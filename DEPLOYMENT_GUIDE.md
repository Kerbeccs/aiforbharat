# DevOps Butler - Deployment Guide

## 🚀 Get Your Shareable Link in 5 Minutes!

### Prerequisites
- GitHub account (free)
- Your AWS credentials from `.env` file

## Quick Deploy Options

### Option 1: Render (Recommended - Free Tier)

1. **Create a Render account**: https://render.com
2. **Connect your GitHub**:
   - Push this code to a GitHub repository
   - Or use Render's "Deploy from Git" option
3. **Create New Web Service**:
   - Click "New +" → "Web Service"
   - Connect your repository
   - Render will auto-detect `render.yaml`
4. **Set Environment Variables** (in Render dashboard):
   - `AWS_ACCESS_KEY_ID`: Your AWS access key
   - `AWS_SECRET_ACCESS_KEY`: Your AWS secret key
   - `AWS_BEARER_TOKEN_BEDROCK`: Your Bedrock API token
   - `AWS_CONSOLE_EMAIL`: Your AWS console email
   - `AWS_CONSOLE_PASSWORD`: Your AWS console password
5. **Deploy**: Click "Create Web Service"
6. **Get your URL**: `https://your-app-name.onrender.com`

### Option 2: Railway (Free $5 Credit)

1. **Create Railway account**: https://railway.app
2. **New Project** → "Deploy from GitHub repo"
3. **Add environment variables** from `.env` file
4. **Deploy** - Railway auto-detects Python
5. **Generate domain** in Settings → Networking

### Option 3: Fly.io (Free Tier)

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Login
flyctl auth login

# Launch app
flyctl launch

# Set secrets
flyctl secrets set AWS_ACCESS_KEY_ID=your_key
flyctl secrets set AWS_SECRET_ACCESS_KEY=your_secret
flyctl secrets set AWS_BEARER_TOKEN_BEDROCK=your_token

# Deploy
flyctl deploy
```

### Option 4: Local Testing

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Run server
python -c "from ui.server import start_server; start_server()"

# Access at: http://localhost:8000
```

## Important Notes

⚠️ **Security Warning**: Your `.env` file contains sensitive credentials. Make sure:
- `.env` is in `.gitignore` (already done)
- Never commit credentials to GitHub
- Use environment variables in production
- Rotate your AWS keys if accidentally exposed

## Environment Variables Required

```
AWS_ACCESS_KEY_ID=your_aws_key
AWS_SECRET_ACCESS_KEY=your_aws_secret
AWS_REGION=us-east-1
AWS_BEARER_TOKEN_BEDROCK=your_bedrock_token
AWS_CONSOLE_EMAIL=your_email
AWS_CONSOLE_PASSWORD=your_password
BEDROCK_CLAUDE_SONNET_MODEL_ID=us.anthropic.claude-sonnet-4-6-20250514-v1:0
BEDROCK_NOVA_LITE_MODEL_ID=amazon.nova-lite-v1:0
MONTHLY_BUDGET_USD=100
LOG_LEVEL=INFO
ENABLE_BROWSER_AUTOMATION=true
```

## Troubleshooting

### Playwright Issues
If browser automation fails, ensure Chromium is installed:
```bash
playwright install chromium
```

### Port Issues
The app uses port 8000 by default. Cloud platforms may override this with `PORT` env var.

### Memory Issues
Browser automation requires ~512MB RAM minimum. Use at least 1GB on cloud platforms.

## Cost Considerations

- **Render Free Tier**: 750 hours/month, sleeps after 15 min inactivity
- **Railway**: $5 free credit, then pay-as-you-go
- **Fly.io**: 3 shared VMs free, 160GB bandwidth
- **AWS Costs**: Your app makes AWS API calls - monitor your AWS billing!

## Next Steps

1. Choose a platform above
2. Push code to GitHub (if using Render/Railway)
3. Set environment variables
4. Deploy and get your shareable link!

Your app will be accessible at a URL like:
- `https://devops-butler.onrender.com`
- `https://devops-butler.up.railway.app`
- `https://devops-butler.fly.dev`

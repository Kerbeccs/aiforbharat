# 🚀 Quick Start - Get Your Shareable Link

## Option 1: Deploy to Render (Easiest - 5 minutes)

### Step 1: Push to GitHub
```bash
# Initialize git (if not already done)
git init
git add .
git commit -m "Initial commit"

# Create a new repo on GitHub, then:
git remote add origin https://github.com/YOUR_USERNAME/devops-butler.git
git push -u origin main
```

### Step 2: Deploy on Render
1. Go to https://render.com and sign up (free)
2. Click "New +" → "Web Service"
3. Connect your GitHub repository
4. Render will auto-detect the `render.yaml` file
5. Click "Create Web Service"

### Step 3: Add Environment Variables
In Render dashboard, go to "Environment" and add:
- `AWS_ACCESS_KEY_ID` = (from your .env file)
- `AWS_SECRET_ACCESS_KEY` = (from your .env file)
- `AWS_BEARER_TOKEN_BEDROCK` = (from your .env file)
- `AWS_CONSOLE_EMAIL` = (from your .env file)
- `AWS_CONSOLE_PASSWORD` = (from your .env file)

### Step 4: Get Your Link! 🎉
Your app will be live at: `https://YOUR-APP-NAME.onrender.com`

---

## Option 2: Test Locally First

### Windows:
```cmd
deploy.bat
```

### Mac/Linux:
```bash
chmod +x deploy.sh
./deploy.sh
```

Then open: http://localhost:8000

---

## Option 3: Railway (Alternative)

1. Go to https://railway.app
2. Click "Start a New Project" → "Deploy from GitHub repo"
3. Select your repository
4. Add environment variables from your `.env` file
5. Railway will auto-deploy
6. Click "Generate Domain" to get your shareable link

---

## Option 4: Fly.io (For Advanced Users)

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Login
flyctl auth login

# Launch (follow prompts)
flyctl launch

# Set secrets
flyctl secrets set AWS_ACCESS_KEY_ID=your_key
flyctl secrets set AWS_SECRET_ACCESS_KEY=your_secret
flyctl secrets set AWS_BEARER_TOKEN_BEDROCK=your_token
flyctl secrets set AWS_CONSOLE_EMAIL=your_email
flyctl secrets set AWS_CONSOLE_PASSWORD=your_password

# Deploy
flyctl deploy
```

---

## ⚠️ Important Security Notes

1. **Never commit your `.env` file** - it's already in `.gitignore`
2. **Use environment variables** in production (not the .env file)
3. **Rotate your AWS keys** if you accidentally expose them
4. **Monitor AWS costs** - this app makes AWS API calls

---

## Troubleshooting

### "Module not found" error
```bash
pip install -r requirements.txt
```

### "Playwright not found" error
```bash
playwright install chromium
```

### Port already in use
Change the port in `start.py` or set `PORT` environment variable

### App crashes on startup
Check your `.env` file has all required variables

---

## What's Next?

Once deployed, you can:
1. Share the link with your team
2. Upload code to deploy
3. Let the AI analyze and deploy automatically
4. Monitor deployments in real-time

## Need Help?

- Check [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for detailed instructions
- Review [README.md](README.md) for architecture details
- Open a GitHub issue for support

---

**Estimated Time to Deploy:**
- Render: 5-10 minutes
- Railway: 5 minutes
- Fly.io: 10-15 minutes
- Local testing: 2 minutes

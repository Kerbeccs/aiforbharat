# ✅ Deployment Checklist

## Before You Deploy

- [ ] Your `.env` file has all AWS credentials filled in
- [ ] You have a GitHub account
- [ ] You've tested the app locally (optional but recommended)
- [ ] You understand the AWS costs (monitor your billing!)

## Files Created for Deployment

✅ All these files are ready in your project:

- `render.yaml` - Render.com configuration
- `Procfile` - Heroku/Railway configuration  
- `runtime.txt` - Python version specification
- `start.py` - Simple startup script
- `deploy.sh` - Local deployment script (Mac/Linux)
- `deploy.bat` - Local deployment script (Windows)
- `.env.example` - Template for environment variables
- `README.md` - Project documentation
- `DEPLOYMENT_GUIDE.md` - Detailed deployment instructions
- `QUICKSTART.md` - Quick start guide
- `DEPLOYMENT_CHECKLIST.md` - This file!

## Deployment Steps (Render - Recommended)

### 1. Push to GitHub
```bash
git init
git add .
git commit -m "Ready to deploy"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

### 2. Create Render Account
- Go to https://render.com
- Sign up with GitHub (free)

### 3. Create Web Service
- Click "New +" → "Web Service"
- Connect your GitHub repository
- Render auto-detects `render.yaml`
- Click "Create Web Service"

### 4. Add Environment Variables
In Render dashboard → Environment tab, add these from your `.env` file:

- [ ] `AWS_ACCESS_KEY_ID`
- [ ] `AWS_SECRET_ACCESS_KEY`
- [ ] `AWS_BEARER_TOKEN_BEDROCK`
- [ ] `AWS_CONSOLE_EMAIL`
- [ ] `AWS_CONSOLE_PASSWORD`

### 5. Deploy!
- Render will automatically build and deploy
- Wait 5-10 minutes for first deployment
- Check the logs for any errors

### 6. Get Your Link
- Your app will be at: `https://YOUR-APP-NAME.onrender.com`
- Share this link with anyone!

## Post-Deployment

- [ ] Test the app by uploading a sample project
- [ ] Monitor AWS costs in AWS Console
- [ ] Set up AWS billing alerts (recommended)
- [ ] Share the link with your team

## Troubleshooting

### Build fails
- Check that all files are committed to GitHub
- Verify `requirements.txt` is present
- Check Render logs for specific errors

### App crashes on startup
- Verify all environment variables are set
- Check that AWS credentials are valid
- Review Render logs

### "Service Unavailable" error
- Render free tier sleeps after 15 min inactivity
- First request after sleep takes ~30 seconds to wake up
- Consider upgrading to paid tier for always-on service

### High AWS costs
- Check your AWS billing dashboard
- Review the `MONTHLY_BUDGET_USD` setting
- Consider setting AWS budget alerts

## Alternative Platforms

If Render doesn't work, try:

1. **Railway** (https://railway.app)
   - Similar to Render
   - $5 free credit
   - Easier domain setup

2. **Fly.io** (https://fly.io)
   - More technical
   - Better for advanced users
   - Free tier with 3 VMs

3. **Heroku** (https://heroku.com)
   - Classic platform
   - No free tier anymore
   - $5-7/month minimum

## Security Reminders

⚠️ **CRITICAL:**
- Never commit `.env` file (already in `.gitignore`)
- Use environment variables in production
- Rotate AWS keys if exposed
- Monitor AWS billing regularly
- Use IAM roles with minimal permissions

## Support

Need help? Check:
- [QUICKSTART.md](QUICKSTART.md) - Quick start guide
- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Detailed guide
- [README.md](README.md) - Project overview
- GitHub Issues - Report problems

---

**Ready to deploy?** Start with [QUICKSTART.md](QUICKSTART.md)!

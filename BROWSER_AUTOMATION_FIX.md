# Browser Automation Fix Guide

## Problem Summary
The browser agent was failing with Pydantic validation errors because:
1. **Nova Lite model** (`amazon.nova-lite-v1:0`) doesn't produce reliable structured outputs
2. Index values were strings `'[12]'` instead of integers `12`
3. Action structures were malformed

## Solution Applied

### 1. Changed LLM Model
**Before:** Nova Lite (cheap but unreliable for structured outputs)
```python
model=self.settings.bedrock_claude_haiku_model_id  # Nova Lite
```

**After:** Claude Sonnet 4.6 (better at structured outputs)
```python
model=self.settings.bedrock_claude_sonnet_model_id  # Claude Sonnet 4.6
```

### 2. Improved Configuration
- Increased `max_tokens` from 1024 to 2048
- Set `temperature` to 0.0 for more deterministic behavior
- Added `max_actions_per_step=10` to prevent infinite loops

## Testing

Run the test script:
```bash
python test_browser.py
```

This will:
1. Login to AWS Console with your credentials
2. Navigate to EKS
3. List clusters
4. Return the result

## Common Issues & Solutions

### Issue 1: "Browser automation requires AWS IAM credentials"
**Solution:** Make sure these are set in `.env`:
```env
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
```

### Issue 2: "browser-use or playwright not installed"
**Solution:** Install dependencies:
```bash
pip install browser-use playwright
playwright install chromium
```

### Issue 3: Still getting validation errors
**Solutions:**
1. **Update browser-use**: `pip install --upgrade browser-use`
2. **Check model availability**: Ensure Claude Sonnet 4.6 is enabled in your AWS account
3. **Fallback to manual**: The system will automatically fall back to manual instructions if browser automation fails

### Issue 4: MFA Required
The browser agent will pause and wait for MFA. You'll need to:
1. Watch the browser window
2. Enter MFA code manually
3. The agent will continue after authentication

## Architecture Flow

```
User Request
    ↓
Code Analyzer (detects what needs deployment)
    ↓
Master Planner (creates deployment plan)
    ↓
Executor Agent (tries CLI first)
    ↓
If CLI not available → Browser Agent
    ↓
Browser Agent:
  1. Opens Chrome via Playwright
  2. Uses Claude Sonnet 4.6 to decide actions
  3. Logs into AWS Console
  4. Performs deployment tasks
  5. Returns results
```

## Model Comparison

| Model | Structured Output | Speed | Cost | Recommendation |
|-------|------------------|-------|------|----------------|
| Nova Lite | ❌ Poor | ⚡ Fast | 💰 Cheap | ❌ Don't use for browser |
| Nova Pro | ⚠️ OK | ⚡ Fast | 💰💰 Medium | ⚠️ Backup option |
| Claude Haiku | ✅ Good | ⚡ Fast | 💰💰 Medium | ✅ Good choice |
| Claude Sonnet 4.6 | ✅ Excellent | 🐌 Slower | 💰💰💰 Expensive | ✅ Best for browser |

## Cost Optimization

If Claude Sonnet is too expensive:
1. Use CLI commands whenever possible (free)
2. Only use browser for tasks that REQUIRE console access
3. Consider Claude Haiku as middle ground
4. Set `MONTHLY_BUDGET_USD` in `.env` to control costs

## Next Steps

1. ✅ UI updated (emojis removed)
2. ✅ Browser agent fixed (using Claude Sonnet)
3. ⏭️ Test with: `python test_browser.py`
4. ⏭️ Run full deployment: `python app.py serve` then upload a project

## Debugging

Enable detailed logging:
```env
LOG_LEVEL=DEBUG
```

Check logs for:
- `[browser_client]` - Browser automation logs
- `[Agent]` - browser-use library logs
- Look for "validation error" or "pydantic" errors

## Alternative: Skip Browser Automation

If you want to skip browser automation entirely:
1. Ensure all AWS CLI credentials are set
2. The system will use CLI for everything
3. Manual tasks will be listed in the final report

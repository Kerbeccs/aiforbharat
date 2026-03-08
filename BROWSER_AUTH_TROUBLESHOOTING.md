# Browser Authentication Troubleshooting

## Current Issue
Error: "The provided model identifier is invalid."

## Root Cause
The browser-use library has authentication issues with certain model IDs when using Bearer Token (API Key) authentication.

## Solutions (Try in Order)

### Solution 1: Use Nova Pro (CURRENT FIX)
✅ **Already applied** - Changed to `amazon.nova-pro-v1:0`

Test with:
```bash
python test_browser.py
```

**Why Nova Pro?**
- No region prefix issues
- Native Amazon model = simpler auth
- Better structured outputs than Nova Lite
- Cheaper than Claude Sonnet

---

### Solution 2: Use IAM Credentials Only (If Solution 1 Fails)

The browser-use library works better with IAM credentials than Bearer Token.

**Update `.env`:**
```env
# Comment out or remove Bearer Token
# AWS_BEARER_TOKEN_BEDROCK=...


```

Then update model to use standard Claude:
```env
BEDROCK_CLAUDE_SONNET_MODEL_ID=anthropic.claude-sonnet-4-6-20250514-v1:0
```
(Remove the "us." prefix)

---

### Solution 3: Use Claude Haiku (Cheaper Alternative)

If Nova Pro doesn't work well, try Claude Haiku:

**In `browser_client.py`, change:**
```python
model_id = self.settings.bedrock_claude_haiku_model_id
```

**In `.env`:**
```env
BEDROCK_CLAUDE_HAIKU_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0
```

---

### Solution 4: Stick with Nova Lite + Better Prompting

If cost is critical, keep Nova Lite but improve the prompts:

**In `browser_client.py`:**
```python
agent = Agent(
    task=(
        f"IMPORTANT: Return valid JSON actions only. "
        f"First go to https://console.aws.amazon.com and login with "
        f"email '{self.settings.aws_console_email}' and "
        f"password '{self.settings.aws_console_password}'. "
        f"If MFA is required, wait and ask the user. "
        f"Then: {instruction}"
    ),
    llm=llm,
    max_actions_per_step=5,  # Reduce to prevent errors
)
```

---

## Model Comparison for Browser-Use

| Model | Auth Compatibility | Structured Output | Cost | Recommendation |
|-------|-------------------|-------------------|------|----------------|
| **Nova Pro** | ✅ Excellent | ✅ Good | 💰💰 Medium | ✅ **Best choice** |
| Claude Sonnet (us.) | ❌ Issues with Bearer Token | ✅ Excellent | 💰💰💰 High | ⚠️ Only with IAM |
| Claude Haiku | ✅ Good | ✅ Good | 💰💰 Medium | ✅ Good alternative |
| Nova Lite | ✅ Good | ❌ Poor | 💰 Cheap | ❌ Not recommended |

---

## Testing Each Solution

After each change, test with:
```bash
python test_browser.py
```

Look for:
- ✅ **Success**: "Browser agent completed task" without errors
- ❌ **Failure**: "The provided model identifier is invalid"
- ⚠️ **Validation errors**: Pydantic errors (means model works but output is bad)

---

## Current Configuration Status

✅ Using Nova Pro (`amazon.nova-pro-v1:0`)
✅ Bearer Token authentication enabled
✅ IAM credentials also available as fallback
✅ Temperature set to 0.0 for deterministic behavior
✅ Max tokens increased to 2048

---

## If All Else Fails

Use CLI-only mode by commenting out browser tasks:

**In `executor/agent.py`:**
```python
# Skip browser tasks
if task.get("requires_browser"):
    logger.info("Skipping browser task, using CLI fallback")
    continue
```

The system will fall back to manual instructions in the final report.

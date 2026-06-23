# Troubleshooting

Common issues and their solutions when setting up and running CTY-Cli.

## "No module named 'main'" when running `cty-cli`

**Symptom**: After `pip install -e .`, running `cty-cli` gives `ModuleNotFoundError: No module named 'main'`.

**Solution**: Use `python main.py` directly from the project directory. The editable install sometimes has issues on Windows. Run:
```powershell
cd C:\Users\dell\cty-cli
python main.py
```

## py_compile fails with "No such file"

**Symptom**: Running `python -m py_compile *.py providers/*.py` fails.

**Cause**: You're not in the project directory.

**Solution**: Always `cd` into the project first:
```powershell
# Wrong (running from home directory):
cd C:\Users\dell
python -m py_compile *.py providers/*.py  # FAILS

# Correct:
cd C:\Users\dell\cty-cli
python -m py_compile *.py providers/*.py  # OK
```

Or use the smoke test script:
```powershell
cd C:\Users\dell\cty-cli
powershell -ExecutionPolicy Bypass -File scripts\smoke_test.ps1
```

## Missing API key

**Symptom**: `ERROR: Missing API key. Set DEEPSEEK_API_KEY in .env or environment.`

**Solution**:
1. Copy `.env.example` to `.env`: `copy .env.example .env`
2. Edit `.env` and add your API key: `DEEPSEEK_API_KEY=sk-your-real-key`
3. Get a DeepSeek API key at https://platform.deepseek.com/api_keys

## `cty-cli --version` doesn't work

**Symptom**: The installed `cty-cli` command doesn't work.

**Solution**: The project is designed to run via `python main.py`. The `cty-cli` console script may have import path issues on some platforms. Use:
```bash
python main.py --version
```

## pytest not found

**Symptom**: `'pytest' is not recognized...`

**Solution**: Install test dependencies:
```bash
pip install pytest
# Or:
pip install -r requirements.txt
```

## "No module named 'ddgs'" when using web_search

**Symptom**: `Error: ddgs not installed.`

**Solution**:
```bash
pip install ddgs
```
This is an optional dependency. If it fails to install, don't worry — the `web_search` tool won't work, but everything else will.

## Streaming doesn't work / tool calling is slow

**Expected behavior**: When tools are provided, DeepSeek and OpenAI-compatible providers switch to **non-streaming mode** for reliability. This means tool decisions are not streamed character-by-character — the response arrives all at once. This is intentional and documented in [docs/architecture.md](architecture.md).

If you need full streaming during tool use, switch to the Anthropic provider:
```
/provider anthropic
```

## File access blocked outside workspace

**Symptom**: `Security blocked: path is outside workspace`

**Solution**: CTY-Cli by default restricts file access to the project directory. To work with files elsewhere:
```bash
python main.py --working-dir C:\path\to\your\project
```

Or if you trust the agent with full filesystem access, you can modify the `PathGuard` initialization in `agent.py` to use `strict=False`.

## Permission prompts are annoying

**Symptom**: You're getting asked for every `write_file` and `execute_command`.

**Solution**: When prompted, type `a` (always allow) to grant session-wide permission for that tool. This persists until you exit.

## Memory search returns nothing

**Symptom**: `/memory search keyword` returns no results but you know you saved memories.

**Cause**: The search is keyword-based, not semantic. If your query doesn't share words with the stored memory, it won't match.

**Solution**: Use more direct keywords or `/memory list` to see all memories and find the right ID.

## .gitignore is not hiding .env

**Symptom**: When running `git status`, `.env` shows as modified.

**Solution**: Make sure `.env` is in `.gitignore` (it should be by default). If it's already tracked:
```bash
git rm --cached .env
git commit -m "Remove .env from tracking"
```

## Windows encoding issues with emoji/special characters

**Symptom**: Garbled characters or errors with Chinese/emoji text.

**Solution**: CTY-Cli uses `sys.stdout.reconfigure(errors="replace")` to handle lone surrogates. If you still see issues, try:
```powershell
chcp 65001  # Set console to UTF-8
$env:PYTHONIOENCODING = "utf-8"
```

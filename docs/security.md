# Security Model

CTY-Cli implements a layered security model: **system prompt guidance** + **permission manager** + **path sandbox** + **command filter**. No single layer is trusted to provide complete safety.

## Layer 1: System Prompt Constraints

The system prompt instructs the model to:
- Never execute destructive commands without confirmation
- Not read/write files outside the project directory
- Report changes when done

**Limitation**: System prompts are advisory only. Models can ignore them, be jailbroken, or make mistakes. This is why Layers 2-4 exist.

## Layer 2: Permission Manager (`permissions.py`)

Three-tier classification:

| Tier | Tools | Behavior |
|------|-------|----------|
| **auto-allow** | `read_file`, `list_files`, `search_code`, `web_search`, `plan_list`, `memory_save`, `memory_recall`, `load_skill` | Executed immediately |
| **ask (write)** | `write_file`, `edit_file`, `plan_create`, `plan_update` | User must approve each call |
| **ask (exec)** | `execute_command` | User must approve each call |

User can respond to permission prompts with:
- `y` — allow this one call
- `n` — deny this call
- `a` — always allow this tool for the rest of the session

Permission decisions are **session-scoped** — they reset on restart.

## Layer 3: Path Sandbox (`security.PathGuard`)

Enforced in every file read/write tool. Cannot be bypassed by the model.

**Always blocked:**
- `.env`, `.env.local`, `.env.production` files
- `.ssh`, `.gnupg`, `.pgp`, `.aws`, `.gcloud`, `.azure` directories
- `.pem`, `.key`, `.pfx`, `.p12`, `.jks`, `.keystore` files
- `C:\Windows`, `/etc`, `/boot`, `/sys`, `/proc` directories

**Workspace boundary (strict mode, default):**
- By default, file access outside the project root is denied
- Exception: `~/.cty-cli/` and `~/.claude/` paths are allowed for memory/skills

## Layer 4: Command Filter (`security.CommandGuard`)

Enforced before every `execute_command` call. Blocks commands matching any of these patterns:

**Destructive filesystem:**
- `rm -rf`, `rm -r /`, `del /s`, `del /f`, `rmdir /s`
- `format`, `fdisk`, `dd if=`, `mkfs`

**System modification:**
- `chmod 777` on root paths, `chown root`
- `sudo`, `su -`, `iptables`
- `systemctl`, service stop/restart/disable
- `reg add/delete`, `regedit`, `diskpart`, `wmic`, `shutdown`, `reboot`
- `net user`, `net localgroup`

**Remote execution:**
- `curl | sh`, `curl | bash`, `wget | bash`
- `Invoke-Expression` (IEX), `iex`

**Credential reading:**
- `cat .env`, `type .env`, `cat id_rsa`, `cat *.pem`
- `scp`, `nc -l` (netcat listener)

## Design Philosophy

- **Belt and suspenders**: The system prompt asks nicely, the permission system asks the user, and the guards enforce hard blocks
- **Tool-layer enforcement**: Guards are checked inside tool functions, not just in the agent loop — even if a tool is called directly, it's still checked
- **Fail-closed**: Unknown paths/commands are blocked by default (strict mode)
- **Transparent**: Blocked operations return clear error messages that the model can relay to the user

## Current Limitations

1. **Not a sandbox**: Commands execute with the user's full filesystem permissions. A determined attacker with model-level access could find workarounds (e.g., encoding commands to bypass regex patterns)
2. **CommandGuard is regex-based**: Sophisticated obfuscation can bypass pattern matching. Production systems should use syscall-level sandboxing (e.g., Docker, gVisor, Firecracker)
3. **No network egress control**: `execute_command` can make arbitrary network requests (curl, wget, etc.)
4. **Session-only permissions**: Always-allow decisions don't persist across sessions

## Future Improvements

- Docker sandbox: execute all commands in an isolated container
- E2B / Firecracker microVM integration
- Network policy: allow/block lists for outbound connections
- Persistent permission profiles per project
- Audit log: write all tool calls and their results to a tamper-evident log

"""Security guards — path sandbox and command safety.

PathGuard: restricts file read/write to the project workspace by default,
blocking access to .env files, .ssh keys, credential files, and system dirs.

CommandGuard: blocks destructive commands (rm -rf, format, etc.), system
config modification, secret reading, and remote-script-execution patterns.
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# ── Sensitive path patterns (always blocked) ──────────────────────────

SENSITIVE_NAMES = {
    ".env", ".env.local", ".env.production", ".env.staging",
    "credentials.json", "credentials", "secrets.json", "secrets.yaml",
    "service-account.json", "service_account.json",
    ".ssh", ".gnupg", ".pgp",
}

SENSITIVE_DIRS = {
    "/etc", "/boot", "/sys", "/proc", "/dev",
    "C:\\Windows", "C:\\Windows\\System32", "C:\\Program Files",
    "C:\\Program Files (x86)",
}

SENSITIVE_EXTENSIONS = {".pem", ".key", ".pfx", ".p12", ".jks", ".keystore"}

# ── Dangerous command patterns ────────────────────────────────────────

DANGEROUS_PATTERNS = [
    # Destructive filesystem
    (re.compile(r"\brm\s+-rf\b", re.IGNORECASE), "rm -rf (recursive force delete)"),
    (re.compile(r"\brm\s+-r\s+/", re.IGNORECASE), "rm -r / (recursive root delete)"),
    (re.compile(r"\bdel\s+/[sS]\b"), "del /s (recursive delete)"),
    (re.compile(r"\bdel\s+/[fF]\b"), "del /f (force delete)"),
    (re.compile(r"\brmdir\s+/[sS]\b", re.IGNORECASE), "rmdir /s (recursive remove)"),
    (re.compile(r"\bformat\b", re.IGNORECASE), "format (disk format)"),
    (re.compile(r"\bfdisk\b", re.IGNORECASE), "fdisk (disk partition)"),
    (re.compile(r"\bdd\s+if=", re.IGNORECASE), "dd (raw disk write)"),
    (re.compile(r"\bmkfs\.", re.IGNORECASE), "mkfs (filesystem creation)"),

    # System modification
    (re.compile(r"\bchmod\s+777\s+/", re.IGNORECASE), "chmod 777 on root path"),
    (re.compile(r"\bchown\s+root\b", re.IGNORECASE), "chown root"),
    (re.compile(r"\bsudo\b", re.IGNORECASE), "sudo (privilege escalation)"),
    (re.compile(r"\bsu\s+-", re.IGNORECASE), "su - (switch user)"),
    (re.compile(r"\biptables\b", re.IGNORECASE), "iptables (firewall modification)"),
    (re.compile(r"\bsystemctl\b", re.IGNORECASE), "systemctl (system service control)"),
    (re.compile(r"\bservice\s+\w+\s+(stop|restart|disable)", re.IGNORECASE), "service stop/restart/disable"),

    # Remote execution
    (re.compile(r"\bcurl\s+.*\|\s*(ba)?sh\b", re.IGNORECASE), "curl | sh (remote script execution)"),
    (re.compile(r"\bwget\s+.*\|\s*(ba)?sh\b", re.IGNORECASE), "wget | sh (remote script execution)"),
    (re.compile(r"\bcurl\s+.*\|\s*bash\b", re.IGNORECASE), "curl | bash (remote script execution)"),
    (re.compile(r"\bwget\s+.*-O\s+-\s*\|\s*(ba)?sh\b", re.IGNORECASE), "wget -O- | sh"),
    (re.compile(r"\bInvoke-Expression\b", re.IGNORECASE), "Invoke-Expression (IEX)"),
    (re.compile(r"\biex\b", re.IGNORECASE), "iex (PowerShell remote execution)"),
    (re.compile(r"\bInvoke-WebRequest\b.*\|\s*iex", re.IGNORECASE), "IWR | iex"),

    # Credential/secret reading
    (re.compile(r"\bcat\s+.*\.env\b", re.IGNORECASE), "cat .env file"),
    (re.compile(r"\btype\s+.*\.env\b", re.IGNORECASE), "type .env file"),
    (re.compile(r"\bcat\s+.*id_rsa\b", re.IGNORECASE), "cat id_rsa"),
    (re.compile(r"\bcat\s+.*\.pem\b", re.IGNORECASE), "cat .pem key"),
    (re.compile(r"\bcopy\s+.*\.env\b", re.IGNORECASE), "copy .env file"),
    (re.compile(r"\bxcopy\s+.*\.env\b", re.IGNORECASE), "xcopy .env file"),
    (re.compile(r"\bscp\b", re.IGNORECASE), "scp (remote file copy)"),
    (re.compile(r"\bnc\s+-[lL]", re.IGNORECASE), "netcat listener"),

    # Registry / Windows system
    (re.compile(r"\breg\s+(add|delete|export|import)\b", re.IGNORECASE), "reg add/delete (registry modification)"),
    (re.compile(r"\bregedit\b", re.IGNORECASE), "regedit (registry editor)"),
    (re.compile(r"\bdiskpart\b", re.IGNORECASE), "diskpart (disk partition tool)"),
    (re.compile(r"\bwmic\b", re.IGNORECASE), "wmic (WMI control)"),
    (re.compile(r"\bshutdown\b", re.IGNORECASE), "shutdown command"),
    (re.compile(r"\breboot\b", re.IGNORECASE), "reboot command"),
    (re.compile(r"\bnet\s+user\b", re.IGNORECASE), "net user (user account manipulation)"),
    (re.compile(r"\bnet\s+localgroup\b", re.IGNORECASE), "net localgroup (group manipulation)"),
]


@dataclass
class GuardResult:
    allowed: bool
    reason: str
    risk_level: str = ""  # "safe", "warning", "dangerous", "blocked"


class PathGuard:
    """Restricts file access to the project workspace.

    Always blocks: .env files, .ssh keys, credential files, system dirs.
    Default-deny for paths outside the project root (configurable).
    """

    def __init__(self, workspace_root: Optional[Path] = None, strict: bool = True):
        self.workspace = (workspace_root or Path.cwd()).resolve()
        self.strict = strict  # If True, deny access outside workspace

    def check_read(self, file_path: str) -> GuardResult:
        return self._check(file_path, "read")

    def check_write(self, file_path: str) -> GuardResult:
        return self._check(file_path, "write")

    def _check(self, file_path: str, operation: str) -> GuardResult:
        try:
            p = Path(file_path).expanduser().resolve()
        except (ValueError, OSError):
            return GuardResult(False, f"Invalid path: {file_path}", "blocked")

        # Always block sensitive names
        if p.name.lower() in {n.lower() for n in SENSITIVE_NAMES}:
            return GuardResult(False, f"Blocked: {p.name} is a sensitive file", "blocked")

        # Always block sensitive extensions
        if p.suffix.lower() in SENSITIVE_EXTENSIONS:
            return GuardResult(False, f"Blocked: {p.suffix} files are restricted", "blocked")

        # Always block sensitive directories
        p_str = str(p)
        for sd in SENSITIVE_DIRS:
            if p_str.lower().startswith(sd.lower()):
                return GuardResult(False, f"Blocked: access to system directory {sd}", "blocked")

        # Check .ssh, .gnupg directories in path
        for part in p.parts:
            if part.lower() in {".ssh", ".gnupg", ".pgp", ".aws", ".gcloud", ".azure"}:
                return GuardResult(False, f"Blocked: access to {part} directory", "blocked")

        # Workspace boundary check
        if self.strict:
            try:
                p.relative_to(self.workspace)
            except ValueError:
                # Allow common dev directories
                allowed_outside = {
                    str(Path.home() / ".cty-cli"),
                    str(Path.home() / ".claude"),
                }
                if not any(p_str.startswith(a) for a in allowed_outside):
                    return GuardResult(
                        False,
                        f"Blocked: {file_path} is outside workspace ({self.workspace}). "
                        f"Use --working-dir or disable strict mode.",
                        "blocked",
                    )

        return GuardResult(True, "ok", "safe")


class CommandGuard:
    """Blocks dangerous shell commands before execution."""

    @staticmethod
    def check(command: str) -> GuardResult:
        if not command or not command.strip():
            return GuardResult(False, "Empty command", "blocked")

        for pattern, description in DANGEROUS_PATTERNS:
            if pattern.search(command):
                return GuardResult(False, f"Blocked: {description}", "blocked")

        return GuardResult(True, "ok", "safe")

"""
agent_waf.py - Coraza WAF Rule Engine Agent

Tests WAF rules against payloads, validates ruleset files, and explains
rule logic. Uses coraza-wasmer CLI when available; falls back to embedded
rule analysis when CLI is not installed.
"""

import asyncio
import json
import os
import re
import subprocess
from typing import Optional

# Embedded WAF rule knowledge base for offline explanation
_RULE_KB = {
    # OWASP CRS rule categories
    "REQUEST-911-METHOD-ENFORCEMENT": {
        "category": "Method Enforcement",
        "description": "Restricts HTTP methods to allowed set (GET, HEAD, POST, OPTIONS by default).",
        "common_ids": ["911100"],
        "examples": 'PUT, DELETE, PATCH methods are blocked unless explicitly allowed.',
    },
    "REQUEST-912-DOS-PROTECTION": {
        "category": "DoS Protection",
        "description": "Detects and blocks denial-of-service patterns like rapid requests, large payloads.",
        "common_ids": ["912100", "912120"],
        "examples": "Requests exceeding body size limits; rapid successive connections.",
    },
    "REQUEST-913-SCANNER-DETECTION": {
        "category": "Scanner Detection",
        "description": "Identifies known vulnerability scanners and attack tools via User-Agent, headers.",
        "common_ids": ["913100", "913101", "913102"],
        "examples": "Nikto, sqlmap, Nessus, Acunetix, OpenVAS User-Agent strings.",
    },
    "REQUEST-920-PROTOCOL-ENFORCEMENT": {
        "category": "Protocol Enforcement",
        "description": "Enforces HTTP protocol compliance: valid methods, headers, URI format.",
        "common_ids": ["920270", "920350", "920420"],
        "examples": "Host header missing, invalid HTTP method, null byte in request.",
    },
    "REQUEST-921-PROTOCOL-ATTACK": {
        "category": "Protocol Attack",
        "description": "Guards against protocol-level attacks: HTTP request smuggling, header injection.",
        "common_ids": ["921110", "921130", "921140"],
        "examples": "CR/LF injection in headers, HTTP request smuggling (CL/TE).",
    },
    "REQUEST-930-APPLICATION-ATTACK-LFI": {
        "category": "Local File Inclusion",
        "description": "Blocks LFI attacks attempting to read local files via directory traversal.",
        "common_ids": ["930110", "930120"],
        "examples": "../../etc/passwd, /proc/self/environ, php://filter wrapper.",
    },
    "REQUEST-931-APPLICATION-ATTACK-RFI": {
        "category": "Remote File Inclusion",
        "description": "Detects RFI attempts that include remote files via http/ftp/php wrappers.",
        "common_ids": ["931100", "931110", "931120"],
        "examples": "include(http://evil.com/shell.txt), ftp://, data:// wrapper exploits.",
    },
    "REQUEST-932-APPLICATION-ATTACK-RCE": {
        "category": "Remote Code Execution",
        "description": "Blocks command injection and RCE patterns (shell commands, eval, exec).",
        "common_ids": ["932100", "932105", "932106", "932150"],
        "examples": "system(), exec(), passthru(), backticks, | pipe, $(cmd) substitutions.",
    },
    "REQUEST-933-APPLICATION-ATTACK-PHP": {
        "category": "PHP Injection",
        "description": "Blocks PHP object injection, serialization attacks, PHP-specific sinks.",
        "common_ids": ["933100", "933120", "933150"],
        "examples": "unserialize(), __wakeup() exploits, phar:// descriptor attacks.",
    },
    "REQUEST-941-APPLICATION-ATTACK-XSS": {
        "category": "Cross-Site Scripting",
        "description": "Detects XSS patterns: script tags, event handlers, javascript: URIs.",
        "common_ids": ["941100", "941110", "941120", "941130"],
        "examples": "<script>alert(1)</script>, onerror=, onload=, javascript:alert().",
    },
    "REQUEST-942-APPLICATION-ATTACK-SQLI": {
        "category": "SQL Injection",
        "description": "Blocks SQL injection patterns: UNION SELECT, OR 1=1, comments, stacked queries.",
        "common_ids": ["942100", "942120", "942130", "942140", "942190"],
        "examples": "UNION SELECT, ' OR '1'='1, --, #, /**/, ; DROP TABLE, WAITFOR DELAY.",
    },
    "REQUEST-943-APPLICATION-ATTACK-SESSION-FIXATION": {
        "category": "Session Fixation",
        "description": "Prevents session fixation attacks where attacker sets a victim's session ID.",
        "common_ids": ["943100"],
        "examples": "PHPSESSID=attacker_controlled in URL query string.",
    },
    "REQUEST-944-APPLICATION-ATTACK-JAVA": {
        "category": "Java Attack",
        "description": "Blocks Java deserialization, JNDI injection, Log4Shell, Spring4Shell.",
        "common_ids": ["944100", "944120", "944130", "944150"],
        "examples": "${jndi:ldap://} (Log4Shell), class.module.classLoader patterns.",
    },
    "REQUEST-949-BLOCKING-EVALUATION": {
        "category": "Blocking Evaluation",
        "description": "Meta-rule that triggers blocking when any previous rule matches at high severity.",
        "common_ids": ["949110", "949111"],
        "examples": "Used as the final 'deny' stage after all detection rules have evaluated.",
    },
}


class WafAgent:
    """Coraza WAF rule engine agent."""

    def __init__(self):
        self._coraza_path = self._find_executable("coraza-wasmer")

    # ------------------------------------------------------------------
    # Handoff entry point
    # ------------------------------------------------------------------
    async def handle_handoff(self, task: dict) -> dict:
        """MCP handoff entry."""
        tool = task.get("tool", "")
        params = task.get("params", {})

        try:
            if tool == "test_rule":
                result = await self.test_rule(
                    rule=params.get("rule", ""),
                    payload=params.get("payload", ""),
                )
            elif tool == "validate_ruleset":
                result = await self.validate_ruleset(
                    rules_path=params.get("rules_path", ""),
                )
            elif tool == "explain_rule":
                result = await self.explain_rule(
                    rule_id=params.get("rule_id", ""),
                )
            else:
                result = {
                    "status": "error",
                    "message": f"Unknown tool: {tool}",
                    "data": None,
                }
        except Exception as e:
            result = {"status": "error", "message": str(e), "data": None}
        return json.dumps(result, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------
    async def test_rule(self, rule: str, payload: str) -> dict:
        """Test a WAF rule against a given payload.

        Args:
            rule: SecLang rule text or rule ID.
            payload: HTTP payload/string to test against the rule.
        """
        if not rule:
            return {"status": "error", "message": "No rule provided", "data": None}
        if not payload:
            return {"status": "error", "message": "No payload provided", "data": None}

        if self._coraza_path:
            return await self._test_rule_via_coraza(rule, payload)
        else:
            return await self._test_rule_local(rule, payload)

    async def validate_ruleset(self, rules_path: str) -> dict:
        """Validate a ruleset file or directory for syntax errors.

        Args:
            rules_path: Path to a .conf ruleset file or directory of rules.
        """
        if not rules_path:
            return {"status": "error", "message": "No rules_path provided", "data": None}
        if not os.path.exists(rules_path):
            return {
                "status": "error",
                "message": f"Path not found: {rules_path}",
                "data": None,
            }

        files = self._collect_rule_files(rules_path)
        if not files:
            return {"status": "error", "message": "No rule files found", "data": None}

        results = []
        all_valid = True

        for fpath in files:
            result = await self._validate_single_file(fpath)
            results.append(result)
            if not result.get("valid", False):
                all_valid = False

        return {
            "status": "ok" if all_valid else ("partial_error" if any(r.get("valid") for r in results) else "error"),
            "message": f"Validated {len(files)} file(s)",
            "data": {
                "valid": all_valid,
                "files": results,
                "total_files": len(files),
                "valid_count": sum(1 for r in results if r.get("valid")),
                "invalid_count": sum(1 for r in results if not r.get("valid")),
            },
        }

    async def explain_rule(self, rule_id: str) -> dict:
        """Explain a WAF rule by its ID.

        Args:
            rule_id: Rule ID (e.g., '932100', 'REQUEST-932-APPLICATION-ATTACK-RCE').
        """
        if not rule_id:
            return {"status": "error", "message": "No rule_id provided", "data": None}

        explanation = self._lookup_rule_kb(rule_id)

        if explanation:
            return {
                "status": "ok",
                "message": f"Found explanation for rule: {rule_id}",
                "data": explanation,
            }

        # Try fuzzy match
        fuzzy = self._fuzzy_match_rule(rule_id)
        if fuzzy:
            return {
                "status": "ok",
                "message": f"Closest match for '{rule_id}'",
                "data": {
                    "query": rule_id,
                    "matched": fuzzy["file"],
                    "explanation": fuzzy,
                    "note": "This is the closest rule category match from the knowledge base.",
                },
            }

        return {
            "status": "error",
            "message": f"No explanation found for rule: {rule_id}",
            "data": {
                "query": rule_id,
                "suggestion": "Try using a numeric rule ID (e.g. 932100) or a CRS rule file name (e.g. REQUEST-932-APPLICATION-ATTACK-RCE).",
            },
        }

    # ------------------------------------------------------------------
    # Internal: coraza CLI
    # ------------------------------------------------------------------
    async def _test_rule_via_coraza(self, rule: str, payload: str) -> dict:
        """Test a rule using the coraza-wasmer CLI."""
        try:
            # Write rule to temp file
            tmp_rule = "/tmp/_coraza_test_rule.conf"
            full_rule = (
                "SecRuleEngine On\n"
                f"SecRule ARGS \"{payload}\" \"{rule}\"\n"
            )
            with open(tmp_rule, "w") as f:
                f.write(full_rule)

            proc = await asyncio.create_subprocess_exec(
                self._coraza_path, "test", "-rules", tmp_rule,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=10
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                stdout, stderr = b"", b""

            try:
                os.unlink(tmp_rule)
            except OSError:
                pass

            out = stdout.decode(errors="replace").strip()
            err = stderr.decode(errors="replace").strip()

            return {
                "status": "ok",
                "message": "Rule tested via coraza-wasmer",
                "data": {
                    "matched": "block" in out.lower() or "deny" in out.lower(),
                    "stdout": out,
                    "stderr": err,
                    "rule": rule,
                    "payload": payload,
                },
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"coraza-wasmer execution failed: {e}",
                "data": None,
            }

    async def _test_rule_local(self, rule: str, payload: str) -> dict:
        """Test a rule against a payload using local pattern matching (no CLI)."""
        matches = []

        # Check for common WAF bypass attempts
        checks = [
            # SQL Injection patterns
            (r"(?i)(union\s+select|select\s+.*from|insert\s+into|'?\s*or\s+'?\d+'?\s*=\s*'?\d|--[#\s]|\bexec\s*\()", "SQL Injection"),
            # XSS patterns
            (r"(?i)(<script|javascript\s*:|on\w+\s*=|\balert\s*\(|eval\s*\(|<img[^>]+onerror)", "XSS"),
            # Path traversal
            (r"(\.\./|\.\.\\|%2e%2e%2f|%2e%2e/|etc/passwd|boot\.ini)", "Path Traversal"),
            # Command injection
            (r"([;|&`]\s*(id|whoami|uname|cat|ls|dir|rm|wget|curl)|\\x[0-9a-f]{2})", "Command Injection"),
            # PHP injection
            (r"(?i)(passthru|shell_exec|system|exec|popen|proc_open|eval\(.*\$)", "PHP Injection"),
            # Log4j / JNDI
            (r"(\$\{.*jndi.*:|\$\{.*:.*\})", "JNDI Injection"),
            # Server-side includes
            (r"(<!--#|<\?php|<\?=)", "SSI/PHP Code Injection"),
            # CRLF injection
            (r"(%0[da]|\\r\\n|\r\n)", "CRLF Injection"),
        ]

        for pattern, vuln_type in checks:
            if re.search(pattern, payload):
                matches.append({"type": vuln_type, "pattern": pattern})

        triggered = len(matches) > 0
        return {
            "status": "ok",
            "message": "Rule test via local pattern matching (coraza-wasmer not available)",
            "data": {
                "matched": triggered,
                "matches": matches,
                "rule": rule,
                "payload": payload,
                "note": "For accurate WAF testing, install coraza-wasmer: https://github.com/corazawaf/coraza-wasmer",
            },
        }

    async def _validate_single_file(self, filepath: str) -> dict:
        """Validate a single ruleset file."""
        try:
            with open(filepath) as f:
                content = f.read()

            issues = []
            warnings = []

            # Check for SecRuleEngine directive
            if not re.search(r'SecRuleEngine\s+On', content, re.MULTILINE):
                warnings.append("No 'SecRuleEngine On' directive found")

            # Check brace matching
            open_braces = content.count("{")
            close_braces = content.count("}")
            if open_braces != close_braces:
                issues.append(f"Brace mismatch: {open_braces} open vs {close_braces} close")

            # Check for common syntax errors
            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Check for unclosed quotes
                quotes = line.count('"')
                if quotes % 2 != 0:
                    issues.append(f"Line {i}: Unbalanced quotes")

            # Try coraza-wasmer validation if available
            if self._coraza_path:
                try:
                    proc = await asyncio.create_subprocess_exec(
                        self._coraza_path, "validate", "-rules", filepath,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    try:
                        stdout, stderr = await asyncio.wait_for(
                            proc.communicate(), timeout=15
                        )
                    except asyncio.TimeoutError:
                        proc.kill()
                        await proc.wait()
                        stdout, stderr = b"", b""
                    if proc.returncode != 0:
                        err = stderr.decode(errors="replace").strip()
                        issues.append(f"coraza validation: {err}")
                except Exception as e:
                    warnings.append(f"Could not run coraza validation: {e}")

            return {
                "file": filepath,
                "valid": len(issues) == 0,
                "issues": issues,
                "warnings": warnings,
            }
        except Exception as e:
            return {
                "file": filepath,
                "valid": False,
                "issues": [str(e)],
                "warnings": [],
            }

    # ------------------------------------------------------------------
    # Internal: rule knowledge base
    # ------------------------------------------------------------------
    def _lookup_rule_kb(self, rule_id: str) -> dict | None:
        """Look up a rule in the embedded knowledge base."""
        # Try exact numeric match
        for key, info in _RULE_KB.items():
            if rule_id in info.get("common_ids", []):
                return {
                    "rule_id": rule_id,
                    "file": key,
                    **info,
                }

        # Try exact filename match
        if rule_id in _RULE_KB:
            return {
                "rule_id": rule_id,
                "file": rule_id,
                **_RULE_KB[rule_id],
            }

        # Try partial filename match
        rule_upper = rule_id.upper()
        for key, info in _RULE_KB.items():
            if rule_upper in key.upper() or any(rule_upper in cid for cid in info.get("common_ids", [])):
                return {
                    "rule_id": rule_id,
                    "matched_as": key,
                    "file": key,
                    **info,
                }

        return None

    def _fuzzy_match_rule(self, rule_id: str) -> dict | None:
        """Find the closest rule category by fuzzy matching."""
        rule_upper = rule_id.upper()

        # Try matching by category name keywords
        keywords_map = {
            "SQL": "REQUEST-942-APPLICATION-ATTACK-SQLI",
            "RCE": "REQUEST-932-APPLICATION-ATTACK-RCE",
            "CMD": "REQUEST-932-APPLICATION-ATTACK-RCE",
            "XSS": "REQUEST-941-APPLICATION-ATTACK-XSS",
            "PHP": "REQUEST-933-APPLICATION-ATTACK-PHP",
            "LFI": "REQUEST-930-APPLICATION-ATTACK-LFI",
            "RFI": "REQUEST-931-APPLICATION-ATTACK-RFI",
            "JAVA": "REQUEST-944-APPLICATION-ATTACK-JAVA",
            "JNDI": "REQUEST-944-APPLICATION-ATTACK-JAVA",
            "Dos": "REQUEST-912-DOS-PROTECTION",
            "SCANNER": "REQUEST-913-SCANNER-DETECTION",
            "PROTOCOL": "REQUEST-920-PROTOCOL-ENFORCEMENT",
            "SESSION": "REQUEST-943-APPLICATION-ATTACK-SESSION-FIXATION",
            "METHOD": "REQUEST-911-METHOD-ENFORCEMENT",
        }

        for keyword, file_key in keywords_map.items():
            if keyword in rule_upper:
                return {
                    "file": file_key,
                    **_RULE_KB.get(file_key, {}),
                }

        return None

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    @staticmethod
    def _find_executable(name: str) -> str | None:
        for path_dir in os.environ.get("PATH", "").split(os.pathsep):
            candidate = os.path.join(path_dir, name)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        for extra in ["/usr/bin", "/usr/local/bin"]:
            candidate = os.path.join(extra, name)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        return None

    @staticmethod
    def _collect_rule_files(path: str) -> list[str]:
        """Collect all .conf rule files from a path."""
        if os.path.isfile(path):
            if path.endswith(".conf"):
                return [path]
            return []

        files = []
        for root, _, filenames in os.walk(path):
            for fn in filenames:
                if fn.endswith(".conf"):
                    files.append(os.path.join(root, fn))
        return sorted(files)

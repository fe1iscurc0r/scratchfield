"""
agent_runtime.py - Falco Runtime Threat Detection Agent

Reads events from a running Falco daemon. Does NOT start Falco.
Attempts falcoctl CLI first; falls back to /var/log/falco-events.json.
Graceful degradation when Falco is not running.
"""

import asyncio
import json
import os
import re
import subprocess
from datetime import datetime, timedelta


class RuntimeAgent:
    """Falco runtime threat detection agent."""

    def __init__(self):
        self._falcoctl_path = self._find_executable("falcoctl")
        self._events_json_path = "/var/log/falco-events.json"
        self._falco_running = None  # cached check

    # ------------------------------------------------------------------
    # Handoff entry point
    # ------------------------------------------------------------------
    async def handle_handoff(self, task: dict) -> dict:
        """MCP handoff entry: task = {"tool": "...", "params": {...}}"""
        tool = task.get("tool", "")
        params = task.get("params", {})

        try:
            if tool == "get_recent_events":
                result = await self.get_recent_events(
                    limit=int(params.get("limit", 50)),
                    priority=params.get("priority"),
                )
            elif tool == "get_event_stats":
                result = await self.get_event_stats(
                    duration=params.get("duration", "1h"),
                )
            elif tool == "check_rule":
                result = await self.check_rule(
                    rule_content=params.get("rule_content", ""),
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
    async def get_recent_events(self, limit: int = 50, priority: str = None) -> dict:
        """Get recent Falco events.

        Args:
            limit: Max number of events (default 50).
            priority: Optional filter ('emergency','alert','critical','error',
                      'warning','notice','informational','debug').
        """
        alive = await self._check_falco_alive()
        if not alive:
            return {
                "status": "error",
                "message": "falco daemon not running",
                "data": None,
            }

        events = []
        if self._falcoctl_path:
            events = await self._get_events_via_falcoctl(limit)
        else:
            events = await self._get_events_via_logfile(limit)

        if priority:
            priority = priority.lower()
            events = [e for e in events if e.get("priority", "").lower() == priority]

        return {
            "status": "ok",
            "message": f"Retrieved {len(events)} events",
            "data": {"events": events[:limit], "total": len(events)},
        }

    async def get_event_stats(self, duration: str = "1h") -> dict:
        """Get event statistics for a time window.

        Args:
            duration: Time window like "1h", "24h", "7d".
        """
        alive = await self._check_falco_alive()
        if not alive:
            return {
                "status": "error",
                "message": "falco daemon not running",
                "data": None,
            }

        since = self._parse_duration(duration)
        events = []
        if self._falcoctl_path:
            events = await self._get_events_via_falcoctl(limit=10000)
        else:
            events = await self._get_events_via_logfile(limit=10000)

        filtered = [e for e in events if self._extract_timestamp(e) >= since]
        stats = self._compute_stats(filtered)

        return {
            "status": "ok",
            "message": f"Stats for last {duration}",
            "data": {
                "duration": duration,
                "total_events": len(filtered),
                "stats": stats,
            },
        }

    async def check_rule(self, rule_content: str) -> dict:
        """Check a Falco rule for syntax validity.

        Args:
            rule_content: The Falco rule text to validate.
        """
        if not rule_content.strip():
            return {
                "status": "error",
                "message": "Empty rule content",
                "data": None,
            }

        issues = []
        warnings = []

        # Basic structural checks
        has_rule = bool(re.search(r'^\s*-\s*rule\s*:', rule_content, re.MULTILINE))
        has_condition = bool(re.search(r'^\s*condition\s*:', rule_content, re.MULTILINE))
        has_desc = bool(re.search(r'^\s*desc\s*:', rule_content, re.MULTILINE))
        has_output = bool(re.search(r'^\s*output\s*:', rule_content, re.MULTILINE))
        has_priority = bool(re.search(r'^\s*priority\s*:', rule_content, re.MULTILINE))

        if not has_rule:
            issues.append("Missing '- rule:' declaration")
        if not has_condition:
            issues.append("Missing 'condition:' field")
        if not has_desc:
            warnings.append("Missing 'desc:' field (recommended)")
        if not has_output:
            warnings.append("Missing 'output:' field")
        if not has_priority:
            warnings.append("Missing 'priority:' field")

        # Check for common macro/list references
        macros = re.findall(r'(?:list|macro):\s*(\S+)', rule_content, re.MULTILINE)
        if macros:
            warnings.append(
                f"Uses external macro/list references: {', '.join(macros)}. "
                "Ensure they are defined."
            )

        # Try falcoctl validation if available
        if self._falcoctl_path:
            try:
                tmp_file = "/tmp/_falco_rule_check.yaml"
                with open(tmp_file, "w") as f:
                    f.write(rule_content)
                proc = await asyncio.create_subprocess_exec(
                    self._falcoctl_path, "rules", "validate", tmp_file,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    stdout, stderr = await asyncio.wait_for(
                        proc.communicate(), timeout=10
                    )
                except TimeoutError:
                    proc.kill()
                    await proc.wait()
                    stdout, stderr = b"", b""
                if proc.returncode != 0:
                    err = stderr.decode(errors="replace").strip()
                    issues.append(f"falcoctl validation error: {err}")
                try:
                    os.unlink(tmp_file)
                except OSError:
                    pass
            except Exception as e:
                warnings.append(f"Could not run falcoctl validation: {e}")

        if issues:
            return {
                "status": "invalid",
                "message": "Rule has issues",
                "data": {"valid": False, "issues": issues, "warnings": warnings},
            }

        return {
            "status": "ok",
            "message": "Rule looks valid" if not warnings else "Rule valid with warnings",
            "data": {"valid": True, "issues": [], "warnings": warnings},
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _find_executable(name: str) -> str | None:
        """Locate an executable in PATH."""
        for path_dir in os.environ.get("PATH", "").split(os.pathsep):
            candidate = os.path.join(path_dir, name)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        # Also try common locations
        for extra in ["/usr/bin", "/usr/local/bin"]:
            candidate = os.path.join(extra, name)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        return None

    async def _check_falco_alive(self) -> bool:
        """Check if Falco daemon is running."""
        if self._falco_running is not None:
            return self._falco_running

        # Check via falcoctl
        if self._falcoctl_path:
            try:
                proc = await asyncio.create_subprocess_exec(
                    self._falcoctl_path, "status",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                try:
                    await asyncio.wait_for(proc.communicate(), timeout=5)
                except TimeoutError:
                    proc.kill()
                    await proc.wait()
                self._falco_running = proc.returncode == 0
                return self._falco_running
            except Exception:
                pass

        # Fallback: check process
        try:
            proc = await asyncio.create_subprocess_exec(
                "pgrep", "-x", "falco",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            except TimeoutError:
                proc.kill()
                await proc.wait()
                stdout = b""
            self._falco_running = proc.returncode == 0 and len(stdout.strip()) > 0
            return self._falco_running
        except Exception:
            pass

        # Fallback: check events log freshness
        if os.path.exists(self._events_json_path):
            try:
                mtime = os.path.getmtime(self._events_json_path)
                if datetime.now().timestamp() - mtime < 300:
                    self._falco_running = True
                    return True
            except OSError:
                pass

        self._falco_running = False
        return False

    async def _get_events_via_falcoctl(self, limit: int) -> list[dict]:
        """Fetch events via falcoctl CLI."""
        try:
            proc = await asyncio.create_subprocess_exec(
                self._falcoctl_path, "events", "list",
                "--limit", str(limit),
                "--output", "json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return []
            if proc.returncode != 0:
                return []
            raw = stdout.decode(errors="replace").strip()
            if not raw:
                return []
            data = json.loads(raw)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("events", data.get("items", []))
            return []
        except Exception:
            return []

    async def _get_events_via_logfile(self, limit: int) -> list[dict]:
        """Fetch events from falco-events.json log file."""
        if not os.path.exists(self._events_json_path):
            return []

        try:
            with open(self._events_json_path) as f:
                raw = f.read()
            # Try JSON-per-line (ndjson)
            lines = raw.strip().split("\n")
            events = []
            for line in lines[-limit * 5:]:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            # Try single JSON array
            if not events:
                data = json.loads(raw)
                if isinstance(data, list):
                    events = data
            return events[-limit:]
        except Exception:
            return []

    @staticmethod
    def _parse_duration(duration: str) -> datetime:
        """Parse a duration string like '1h', '24h', '7d' into a datetime."""
        now = datetime.now()
        match = re.match(r'^(\d+)\s*(s|m|h|d|w)$', duration.strip())
        if not match:
            return now - timedelta(hours=1)
        val = int(match.group(1))
        unit = match.group(2)
        if unit == 's':
            return now - timedelta(seconds=val)
        elif unit == 'm':
            return now - timedelta(minutes=val)
        elif unit == 'h':
            return now - timedelta(hours=val)
        elif unit == 'd':
            return now - timedelta(days=val)
        elif unit == 'w':
            return now - timedelta(weeks=val)
        return now - timedelta(hours=1)

    @staticmethod
    def _extract_timestamp(event: dict) -> datetime:
        """Extract timestamp from a Falco event dict."""
        ts = event.get("output_fields", {}).get("evt.time")
        if ts is None:
            ts = event.get("timestamp")
        if ts is None:
            ts = event.get("time")

        if ts is None:
            return datetime.min

        if isinstance(ts, str):
            try:
                # Try ISO format
                if "T" in ts:
                    ts = ts.replace("Z", "+00:00")
                    return datetime.fromisoformat(ts).replace(tzinfo=None)
                # Try nanosecond epoch
                ns = int(ts)
                if ns > 1_000_000_000_000_000_000:
                    ns //= 1_000_000_000
                return datetime.fromtimestamp(ns)
            except (ValueError, OSError):
                pass
        if isinstance(ts, (int, float)):
            if ts > 1_000_000_000_000_000_000:
                ts = ts / 1_000_000_000
            return datetime.fromtimestamp(ts)

        return datetime.min

    @staticmethod
    def _compute_stats(events: list[dict]) -> dict:
        """Compute statistics from a list of Falco events."""
        priority_counts = {}
        rule_counts = {}
        for e in events:
            p = e.get("priority", "unknown")
            priority_counts[p] = priority_counts.get(p, 0) + 1
            r = e.get("rule", "unknown")
            rule_counts[r] = rule_counts.get(r, 0) + 1

        # Top rules
        top_rules = sorted(rule_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "by_priority": priority_counts,
            "top_rules": [{"rule": r, "count": c} for r, c in top_rules],
        }

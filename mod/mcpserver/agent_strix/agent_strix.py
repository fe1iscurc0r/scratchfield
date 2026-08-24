"""agent_strix - Pentest toolkit (atomic operations).

Decomposed from Strix pentest orchestrator into individual, composable tools.
Each tool wraps standard pentest CLI binaries (nmap, hydra, searchsploit, etc.).
No stateful orchestrator — every call is self-contained by default.

Tools:
  - port_scan:     nmap-based port discovery
  - service_detect: banner grab / service fingerprint on a specific port
  - vuln_scan:     searchsploit / CVE lookup for a given service+version
  - exploit_check: verify if target is vulnerable to a specific CVE
  - brute_force:   hydra-based credential brute force
  - report:        aggregate results from a scan_id into a structured report
"""

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
import uuid

logger = logging.getLogger(__name__)

# ── Report store cap ─────────────────────────────────────────────────────
_MAX_REPORT_ENTRIES = 1000  # Maximum number of scan sessions before eviction

# ── Tool availability checks ────────────────────────────────────────────

def _find_tool(name: str) -> str | None:
    """Return full path to tool if available, else None."""
    if shutil.which(name):
        return name
    # Alternative names
    alt_names = {
        "searchsploit": ["searchsploit"],
        "hydra": ["hydra"],
    }
    for alt in alt_names.get(name, []):
        if shutil.which(alt):
            return alt
    return None


def _check_tool(name: str) -> str | None:
    """Return error message string if tool is missing, else None."""
    if not _find_tool(name):
        return f"Tool '{name}' is not installed or not in PATH. Install with your package manager."
    return None


# ── Report store (simple in-memory dict with max-size cap) ─────────────

_report_store: dict[str, list[dict]] = {}


def _store_result(scan_id: str, tool: str, result: dict):
    """Accumulate results under a scan_id for final reporting.
    Evicts oldest entries when the store exceeds _MAX_REPORT_ENTRIES.
    """
    if scan_id not in _report_store:
        _report_store[scan_id] = []
    _report_store[scan_id].append({"tool": tool, "result": result})

    # Evict oldest scan IDs when over the cap
    while len(_report_store) > _MAX_REPORT_ENTRIES:
        oldest = next(iter(_report_store))
        del _report_store[oldest]


def _get_results(scan_id: str) -> list[dict]:
    return _report_store.get(scan_id, [])


def _clear_results(scan_id: str):
    _report_store.pop(scan_id, None)


# ── Async subprocess helper ────────────────────────────────────────────

async def _run_async(cmd: list[str], timeout: float = 60) -> tuple[str, str, int]:
    """Run a command asynchronously and return (stdout, stderr, returncode).
    Kills the process on timeout to prevent zombie subprocesses.
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise subprocess.TimeoutExpired(cmd, timeout)
    return (
        stdout.decode(errors="replace"),
        stderr.decode(errors="replace"),
        proc.returncode or 0,
    )


# ── Agent ────────────────────────────────────────────────────────────────


class StrixAgent:
    """Pentest toolkit: atomic nmap/hydra/searchsploit operations.

    Decomposed from Strix pentest orchestrator — no orchestration state,
    just pure tool wrappers that compose freely.
    """

    async def handle_handoff(self, task: dict) -> dict:
        """Route handoff to the requested tool.

        Expected format:
            {"tool": "...", "args": {...}}

        Returns:
            {"status": "ok"|"error", "message": "...", "data": ...}
        """
        tool = task.get("tool", "")
        args = task.get("args", {})

        handlers = {
            "port_scan": self._port_scan,
            "service_detect": self._service_detect,
            "vuln_scan": self._vuln_scan,
            "exploit_check": self._exploit_check,
            "brute_force": self._brute_force,
            "report": self._report,
        }

        handler = handlers.get(tool)
        if handler is None:
            return {
                "status": "error",
                "message": f"Unknown tool: {tool}. Available: {list(handlers.keys())}",
                "data": None,
            }

        try:
            return await handler(args)
        except subprocess.TimeoutExpired:
            return {"status": "error", "message": "Tool timed out", "data": None}
        except Exception as e:
            logger.error("Error in tool %s: %s", tool, e)
            return {"status": "error", "message": str(e), "data": None}

    # ── Tools ──────────────────────────────────────────────────────────

    async def _port_scan(self, args: dict) -> dict:
        """Run an nmap port scan.

        Args:
            target: Target IP or hostname. Required.
            ports: Port range (e.g. "1-1000", "80,443"). Default "1-1000".
            scan_id: Optional scan ID for report aggregation. Auto-generated if omitted.
        """
        err = _check_tool("nmap")
        if err:
            return {"status": "error", "message": err, "data": None}

        target = args.get("target")
        if not target:
            return {"status": "error", "message": "Must provide 'target'", "data": None}

        ports = args.get("ports", "1-1000")
        scan_id = args.get("scan_id", str(uuid.uuid4()))

        cmd = ["nmap", "-sS", "-sV", "-p", str(ports), "--open", "-oX", "-", target]

        logger.info("Running: %s", " ".join(cmd))
        try:
            stdout, stderr, rc = await _run_async(cmd, timeout=120)
        except subprocess.TimeoutExpired:
            return {"status": "error", "message": "Port scan timed out (120s)", "data": None}

        if rc != 0 and not stdout.strip():
            return {"status": "error", "message": stderr.strip() or "nmap failed", "data": None}

        # Parse XML output for structured results
        ports_found = self._parse_nmap_xml(stdout)

        result = {
            "scan_id": scan_id,
            "target": target,
            "ports_scanned": str(ports),
            "open_ports": ports_found,
        }
        _store_result(scan_id, "port_scan", result)

        return {
            "status": "ok",
            "message": f"Found {len(ports_found)} open port(s) on {target}",
            "data": result,
        }

    async def _service_detect(self, args: dict) -> dict:
        """Detect service/version on a specific port.

        Args:
            target: Target IP or hostname. Required.
            port: Port number. Required.
            scan_id: Optional scan ID for report aggregation.
        """
        err = _check_tool("nmap")
        if err:
            return {"status": "error", "message": err, "data": None}

        target = args.get("target")
        port = args.get("port")

        if not target or port is None:
            return {"status": "error", "message": "Must provide 'target' and 'port'", "data": None}

        scan_id = args.get("scan_id", str(uuid.uuid4()))

        cmd = ["nmap", "-sV", "--version-intensity", "5", "-p", str(port), "-oX", "-", target]

        try:
            stdout, stderr, rc = await _run_async(cmd, timeout=60)
        except subprocess.TimeoutExpired:
            return {"status": "error", "message": "Service detection timed out (60s)", "data": None}

        if rc != 0 and not stdout.strip():
            return {"status": "error", "message": stderr.strip() or "nmap failed", "data": None}

        svc = self._parse_nmap_xml(stdout)
        result = {"scan_id": scan_id, "target": target, "port": port, "service": svc[0] if svc else None}
        _store_result(scan_id, "service_detect", result)

        return {
            "status": "ok",
            "message": f"Service on {target}:{port} → {svc}" if svc else f"No service identified on {target}:{port}",
            "data": result,
        }

    async def _vuln_scan(self, args: dict) -> dict:
        """Look up known vulnerabilities for a service.

        Args:
            target: Target (for context in report). Required.
            service: Service name (e.g. "OpenSSH 7.4"). Required.
            scan_id: Optional scan ID.
        """
        err = _check_tool("searchsploit")
        if err:
            return {"status": "error", "message": err, "data": None}

        target = args.get("target", "unknown")
        service = args.get("service")
        if not service:
            return {"status": "error", "message": "Must provide 'service'", "data": None}

        scan_id = args.get("scan_id", str(uuid.uuid4()))

        # searchsploit with JSON output
        cmd = ["searchsploit", "--json", service]

        try:
            stdout, stderr, rc = await _run_async(cmd, timeout=30)
        except subprocess.TimeoutExpired:
            return {"status": "error", "message": "Vulnerability scan timed out (30s)", "data": None}

        if rc != 0:
            return {"status": "error", "message": stderr.strip() or "searchsploit failed", "data": None}

        try:
            raw = json.loads(stdout)
            exploits = raw.get("RESULTS_EXPLOIT", []) + raw.get("RESULTS_SHELLCODE", [])
            # Deduplicate by EDB-ID
            seen = set()
            unique = []
            for e in exploits:
                eid = e.get("EDB-ID")
                if eid and eid not in seen:
                    seen.add(eid)
                    unique.append({
                        "edb_id": eid,
                        "title": e.get("Title", ""),
                        "path": e.get("Path", ""),
                        "type": e.get("Type", ""),
                        "platform": e.get("Platform", ""),
                    })
        except json.JSONDecodeError:
            unique = []

        result = {
            "scan_id": scan_id,
            "target": target,
            "service": service,
            "vulnerabilities": unique,
            "count": len(unique),
        }
        _store_result(scan_id, "vuln_scan", result)

        return {
            "status": "ok",
            "message": f"Found {len(unique)} exploit(s) for {service}",
            "data": result,
        }

    async def _exploit_check(self, args: dict) -> dict:
        """Check if a target is likely vulnerable to a specific CVE.

        Args:
            target: Target IP/hostname. Required.
            cve_id: CVE identifier (e.g. "CVE-2021-41773"). Required.
            scan_id: Optional scan ID.
        """
        err_nmap = _check_tool("nmap")
        err_sploit = _check_tool("searchsploit")
        if err_nmap or err_sploit:
            return {"status": "error", "message": err_nmap or err_sploit, "data": None}

        target = args.get("target")
        cve_id = args.get("cve_id")

        if not target or not cve_id:
            return {"status": "error", "message": "Must provide 'target' and 'cve_id'", "data": None}

        scan_id = args.get("scan_id", str(uuid.uuid4()))

        # Check for known exploits referencing this CVE
        cmd = ["searchsploit", "--json", cve_id]
        exploits_found = []
        try:
            stdout, _, _ = await _run_async(cmd, timeout=30)
            try:
                raw = json.loads(stdout)
                exploits_found = raw.get("RESULTS_EXPLOIT", [])
            except json.JSONDecodeError:
                pass
        except subprocess.TimeoutExpired:
            pass

        # Quick nmap check for common ports
        cmd_nmap = ["nmap", "-F", "-oX", "-", target]
        open_ports = []
        try:
            stdout_nmap, _, rc_nmap = await _run_async(cmd_nmap, timeout=60)
            if rc_nmap == 0:
                open_ports = self._parse_nmap_xml(stdout_nmap)
        except subprocess.TimeoutExpired:
            pass

        result = {
            "scan_id": scan_id,
            "target": target,
            "cve_id": cve_id,
            "exploits_available": len(exploits_found),
            "exploits": [{"edb_id": e.get("EDB-ID"), "title": e.get("Title")} for e in exploits_found[:10]],
            "open_ports": open_ports,
            "verdict": "likely_vulnerable" if exploits_found and open_ports else ("potential" if exploits_found else "no_exploit_available"),
        }
        _store_result(scan_id, "exploit_check", result)

        return {"status": "ok", "message": f"CVE {cve_id} check for {target} complete", "data": result}

    async def _brute_force(self, args: dict) -> dict:
        """Run hydra brute-force against a service.

        Args:
            target: Target IP/hostname. Required.
            service: Service name (e.g. "ssh", "ftp", "http-post-form"). Required.
            userlist: Path to username wordlist. Required.
            passlist: Path to password wordlist. Required.
            port: Port number. Optional (uses default for service).
            extra_args: Additional hydra arguments. Optional.
            scan_id: Optional scan ID.
        """
        err = _check_tool("hydra")
        if err:
            return {"status": "error", "message": err, "data": None}

        target = args.get("target")
        service = args.get("service")
        userlist = args.get("userlist")
        passlist = args.get("passlist")

        if not all([target, service, userlist, passlist]):
            return {
                "status": "error",
                "message": "Must provide 'target', 'service', 'userlist', 'passlist'",
                "data": None,
            }

        # Validate wordlist files exist
        for f, name in [(userlist, "userlist"), (passlist, "passlist")]:
            if not os.path.isfile(f):
                return {"status": "error", "message": f"{name} file not found: {f}", "data": None}

        scan_id = args.get("scan_id", str(uuid.uuid4()))
        port = args.get("port")
        extra = args.get("extra_args", "")

        cmd = ["hydra", "-L", userlist, "-P", passlist]
        if port:
            cmd.extend(["-s", str(port)])
        if extra:
            cmd.extend(extra.split())
        cmd.extend([target, service])

        logger.info("Running hydra on %s:%s", target, service)
        try:
            stdout, stderr, _ = await _run_async(cmd, timeout=300)
        except subprocess.TimeoutExpired:
            return {"status": "error", "message": "Brute force timed out (300s)", "data": None}

        # Parse hydra output for found credentials
        credentials = self._parse_hydra_output(stdout, stderr)

        result = {
            "scan_id": scan_id,
            "target": target,
            "service": service,
            "port": port,
            "credentials_found": credentials,
            "raw_output": (stdout + stderr)[-4000:],  # last 4KB
        }
        _store_result(scan_id, "brute_force", result)

        return {
            "status": "ok",
            "message": f"Brute force on {target}:{service} complete — {len(credentials)} credential(s) found",
            "data": result,
        }

    async def _report(self, args: dict) -> dict:
        """Generate an aggregated report from a scan_id.

        Args:
            scan_id: The scan session ID to report on. Required.
        """
        scan_id = args.get("scan_id")
        if not scan_id:
            return {"status": "error", "message": "Must provide 'scan_id'", "data": None}

        results = _get_results(scan_id)
        if not results:
            return {"status": "error", "message": f"No results found for scan_id: {scan_id}", "data": None}

        # Aggregate by tool
        summary = {}
        open_ports = []
        vulnerabilities = []
        credentials = []

        for entry in results:
            tool = entry["tool"]
            r = entry["result"]
            if tool == "port_scan":
                open_ports.extend(r.get("open_ports", []))
            elif tool == "vuln_scan":
                vulnerabilities.extend(r.get("vulnerabilities", []))
            elif tool == "brute_force":
                credentials.extend(r.get("credentials_found", []))

        report = {
            "scan_id": scan_id,
            "tool_calls": len(results),
            "tools_used": list({e["tool"] for e in results}),
            "open_ports": open_ports,
            "vulnerability_count": len(vulnerabilities),
            "vulnerabilities": vulnerabilities,
            "credentials_found": credentials,
            "raw_results": results,
        }

        return {"status": "ok", "message": f"Report for {scan_id} generated", "data": report}

    # ── Parsers ────────────────────────────────────────────────────────

    @staticmethod
    def _parse_nmap_xml(xml_output: str) -> list[dict]:
        """Minimal nmap XML → list of open port dicts. No external deps."""
        import xml.etree.ElementTree as ET
        ports = []
        try:
            root = ET.fromstring(xml_output)
            for host in root.findall("host"):
                addr_elem = host.find("address")
                ip = addr_elem.get("addr", "") if addr_elem is not None else ""
                for port_elem in host.findall(".//port"):
                    state = port_elem.find("state")
                    if state is not None and state.get("state") == "open":
                        svc = port_elem.find("service")
                        ports.append({
                            "ip": ip,
                            "port": int(port_elem.get("portid", 0)),
                            "protocol": port_elem.get("protocol", ""),
                            "service": svc.get("name", "") if svc is not None else "",
                            "product": svc.get("product", "") if svc is not None else "",
                            "version": svc.get("version", "") if svc is not None else "",
                        })
        except ET.ParseError:
            pass
        return ports

    @staticmethod
    def _parse_hydra_output(stdout: str, stderr: str) -> list[dict]:
        """Extract found credentials from hydra output."""
        creds = []
        combined = stdout + stderr
        for line in combined.splitlines():
            # Hydra success lines contain "login:" and "password:"
            if "login:" in line.lower() and "password:" in line.lower():
                # Try to extract host login password
                try:
                    parts = line.strip().split()
                    login_part = None
                    pass_part = None
                    host_part = None
                    for i, p in enumerate(parts):
                        if p.lower() == "login:":
                            login_part = parts[i + 1] if i + 1 < len(parts) else ""
                        if p.lower() == "password:":
                            pass_part = parts[i + 1] if i + 1 < len(parts) else ""
                        host_part = parts[1].strip("[]") if len(parts) > 1 else ""
                    if login_part and pass_part:
                        creds.append({"host": host_part, "username": login_part, "password": pass_part})
                except (IndexError, ValueError):
                    creds.append({"raw": line.strip()})
        return creds

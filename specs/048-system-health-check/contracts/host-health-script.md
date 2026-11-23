# Contract: Windows Health Script and Host Run Artifacts

## Reviewed script

| Field | Rule |
|---|---|
| Source | `windows/health-check.ps1` |
| Host path | `C:\ProgramData\agentic-rag\health\health-check.ps1` |
| Output directory | `C:\ProgramData\agentic-rag\health\reports` |
| Hash | SHA-256 pinned in `src/agentic_rag_mcp/mcp_action/health.py` and checked before execution |
| Mode | Strictly read-only diagnostic |
| Launcher | Fixed wrapper only; no model-authored path/command/argument |
| Monitor | Script runs with `-NoReliabilityMonitor`; Reliability Monitor is opened by the reviewed action |

Deployment copies the source script to the fixed host path and verifies the copied hash. Missing/mismatched hash, missing directory, denied execution policy, or unavailable host fails closed before offering/running.

## Read-only rule

The script may use read-only inventory/health queries: CIM/WMI reads, event-log reads, file/registry reads, Get-* read-only commands, process/service queries, and Reliability Records. It must not use `Set-*`, `New-*` (except its own output files), `Remove-*` outside its own run artifacts, `Start-Process`, service start/stop/restart, `Invoke-CimMethod`, registry writes, `reg add`, `runas`, `schtasks /change`, `net user` modifications, `Get-Credential`, `Read-Host`, installers, or repair commands.

The only writes are the requested JSON/HTML report artifacts, including the complete HTML copy at `%LOCALAPPDATA%\Temp\selfcheck.html`. Report artifacts are new tool-owned files; no user files, registry values, services, settings, or applications may be changed.

## Invocation and run identity

- Sidecar generates `run_id = uuid4().hex` (lowercase 32 hex); model cannot supply it.
- Fixed wrapper verifies `^[0-9a-f]{32}$`.
- Wrapper runs exactly:

```text
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File <fixed-script-path> -NoReliabilityMonitor -ReportPath <fixed-html-path>
```

- Child process deadline: 120 seconds. On timeout, kill only the health-check child and report timeout; never leave an unbounded process.
- The wrapper captures the script’s single-line JSON stdout and writes UTF-8 without BOM to `<runId>.json`.
- The script writes `<runId>.html` to the fixed report directory.
- The wrapper emits only a small marked status object, under 4,000 characters, containing run ID, exit code, and file existence. No large JSON/HTML/path/desktop text is sent through the Windows-MCP text result.
- Host artifacts are read by the sidecar at `/mnt/c/ProgramData/agentic-rag/health/reports/...`. Production deploy mounts `/mnt/c` read-only; standalone compose must document/add the mount for local runs.

## Artifact validation

- JSON exists, is non-empty, valid UTF-8, parses to an object, and contains required health/reliability/inventory sections within size/depth/array/string caps.
- HTML exists, is non-empty, valid UTF-8, complete HTML, ≤5 MiB, and passes report content rules.
- Invalid/oversized/malformed/truncated output is an honest action error; no partial “ok” and no fabricated report.
- After successful report publication, a fixed cleanup call removes only `<runId>.json` and `<runId>.html`. Cleanup failure is sanitized and never deletes unrelated files; the URL still expires.

## Failure behavior

| Condition | Result |
|---|---|
| Missing script/hash mismatch | `error`, fail closed before diagnostics |
| Execution policy denied | `error`, no policy change/fallback to Invoke-Expression |
| Host offline/child timeout | `error` or `partial` depending on whether a valid summary was obtained; no infinite wait |
| JSON missing/malformed/truncated/oversized | `error`; no score/report claim |
| HTML missing/invalid/oversized | summary may be returned with report `failed`; action `partial` |
| Reliability data unavailable | explicit skipped reliability/check status; confidence reduced/low; never fabricated |
| Cleanup failure | report URL remains temporary; sanitized cleanup warning; no user file touched |

## Audit and privacy

Audit only the run outcome, overall status, score, counts, confidence, report `published|failed|skipped`, display/screenshot status, and timings. Never audit the run ID, host paths, script contents, JSON/HTML, report URL/token, login, email, IP, serial, password-expiry detail, event text, crash text, or credentials.

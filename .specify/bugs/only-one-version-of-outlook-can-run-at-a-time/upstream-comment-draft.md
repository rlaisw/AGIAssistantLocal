# Upstream comment draft — hermes-agent issue #148459

Not posted: the current GitHub PAT (fine-grained, account rlaisw) returned
`Resource not accessible by personal access token (addComment)`. Post manually
or with a token that has write access to NousResearch/hermes-agent:

```
gh issue comment 148459 --repo NousResearch/hermes-agent --body <this text>
```

---

Update (2026-11-05): the MCP-over-SSE degradation is now **intermittent within
minutes and no longer cleared by recovery**.

Evidence from today's session (UTC timestamps from our audit log):

- 05:39:50 — RunningApps returned `[Word, Excel, PowerPoint]` while Outlook was
  demonstrably running (the result-corruption signature from my earlier
  comment). The downstream agent launched Outlook on that bad data and Windows
  blocked the second instance with the "Only one version of Outlook" dialog.
- 05:45:33 — fresh session, fresh gateway: RunPython code arguments dropped on
  5 consecutive calls (empty-args → default echo). Args-free tools (RunningApps,
  AvailableApps) kept working in the same degraded state.
- 05:54:06 — same session, minutes later: RunPython arguments delivered
  correctly again (a process probe returned real data), i.e. the degradation
  toggles on/off within a single session.

Recovery (`hermes mcp remove` + `hermes mcp add` + `hermes gateway restart -y
--detach`, including a full restart of the MCP server itself) previously
cleared this every time; today it did not restore argument delivery.
Previously the defect appeared only after hours of session uptime.

Observation that may help localize: in every occurrence, calls **without**
arguments succeed and calls **with** arguments behave as if the arguments were
absent — which points at the argument serialization in the client session, not
the transport connection itself.

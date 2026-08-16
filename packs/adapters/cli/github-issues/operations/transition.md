---
schema: "agora/tool-operation/v1"
id: "transition"
name: "Transition a GitHub issue"
capability: "issue.transition"
risk: "write"
arguments: ["issue","{state}","{issue}"]
inputs: ["issue","state"]
input-values: {"state":["close","reopen"]}
result-kind: "work-item-transition"
---

# Transition a GitHub issue

Closes or reopens one issue. The allowed-value rule prevents the dynamic argument from selecting any
other GitHub issue subcommand.

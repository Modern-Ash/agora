---
schema: "agora/tool-operation/v1"
id: "transition"
name: "Transition a Jira work item"
capability: "issue.transition"
risk: "write"
arguments: ["jira","workitem","transition","--key","{issue}","--status","{state}","--yes","--json"]
inputs: ["issue","state"]
result-kind: "work-item-transition"
---

# Transition a Jira work item

Transitions one work item to an available workflow status without an interactive confirmation.
Jira still enforces its workflow permissions, conditions, and validators.

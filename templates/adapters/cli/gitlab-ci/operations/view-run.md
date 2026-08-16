---
schema: "agora/tool-operation/v1"
id: "view-run"
name: "View a GitLab pipeline run"
capability: "ci.read"
risk: "read"
arguments: ["ci","get","--pipeline-id","{run}","--with-job-details","--output","json"]
inputs: ["run"]
result-kind: "pipeline-run"
---

# View a GitLab pipeline run

Returns one pipeline and its job details as JSON without requesting CI/CD variables or job logs.

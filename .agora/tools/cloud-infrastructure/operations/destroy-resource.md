---
schema: "agora/tool-operation/v1"
id: "destroy-resource"
name: "Destroy a cloud resource"
capability: "cloud.destroy"
risk: "destructive"
environment-required: true
arguments: ["resource","destroy","{resource}","--environment","{environment}","--output","json"]
inputs: ["resource","environment"]
result-kind: "cloud-destruction"
---

# Destroy a cloud resource

Destroys one external resource. No bundled Method Pack role receives `cloud.destroy` by default.

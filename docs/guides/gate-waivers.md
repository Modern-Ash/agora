# Granular Gate Waivers

Agora normally requires every obligation declared by a transition gate. When delivery must proceed
with an explicitly accepted residual risk, a Method Pack role may receive `gate.waive` authority.
The resulting `WAIVER.md` names the exact missing obligations; it cannot bypass a transition edge,
role restriction, WIP limit, child-work closure rule, or work operational status.

## Authorize an exception

The bundled Scrum Product Owner and Kanban Service Request Manager roles grant `gate.waive`. A
waiver requires a reason, at least one durable risk-evidence reference, and one or more outstanding
obligations:

```bash
agora gate waive \
  --id accepted-release-risk \
  --swarm payments \
  --work release-candidate \
  --gate completion \
  --criterion load-test \
  --artifact performance-report \
  --successful-evidence \
  --approval product-owner \
  --reason "The incident deadline was accepted by product governance" \
  --evidence repo://risk/accepted-release-risk.md \
  --by product-owner
```

Agora rejects criteria not declared by the work, artifact kinds not required by the work, approval
roles not required by the gate, requirements already satisfied or waived, and evidence waivers for
gates that do not require successful evidence. An empty waiver or a waiver without risk evidence is
also invalid.

The record is stored at:

```text
.agora/swarms/<swarm>/work/<work>/waivers/<id>/WAIVER.md
```

Inspect decisions with `agora gate list --swarm payments --work release-candidate`. Work-scoped
agent sessions include every applicable `WAIVER.md` in required reading.

## Require a signed decision

An actor configured with authentication cannot create the record directly. Prepare the exact
intent, export its canonical authorization payload, sign it outside Agora, and apply it:

```bash
agora gate waive-prepare \
  --action-id waive-release-risk \
  --id accepted-release-risk \
  --swarm payments --work release-candidate --gate completion \
  --criterion load-test \
  --reason "Product governance accepted the residual risk" \
  --evidence repo://risk/accepted-release-risk.md \
  --by authenticated-owner

agora action authorization --action waive-release-risk --output /tmp/waiver.json
# Sign /tmp/waiver.json with the actor's external Ed25519 private key.
agora action apply --action waive-release-risk --signature /tmp/waiver.sig
```

The applied `ACTION.md` and `WAIVER.md` cross-reference one another. Apply rechecks current Method
Pack authority, work mutability, gate policy, and every named outstanding obligation. Work digests
include existing waivers, so a previously prepared transition becomes stale when the exception set
changes.

## Customize authority

Add `gate.waive` only to roles that can accept residual delivery risk:

```yaml
allowed-actions: ["work.transition", "gate.waive"]
```

Keep technical evidence production separate from exception authority when the development process
requires independent acceptance. Agora records the decision; external review, expiry, environment
classification, and organization-specific risk taxonomies remain Method Pack or repository policy.


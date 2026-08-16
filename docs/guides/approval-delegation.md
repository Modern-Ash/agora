# Approval Delegation

Agora can delegate one role approval without transferring the role itself. An Approval Delegation
is limited to one swarm, work item, and role. It names one compatible target actor, is single-use,
and ends as `used` or `revoked`. The grantor remains assigned to the role throughout the lifecycle.

This is intentionally narrower than a handoff. A handoff changes who holds a role; an Approval
Delegation grants only the authority to create one `approval.add` record for the named work.

## Grant and use authority

The role holder needs `approval.delegate`, while the delegated role must itself grant
`approval.add`. The target may be a human, AI agent, or swarm actor, but must satisfy the role's
actor-kind and capability contract:

```bash
agora approval delegate \
  --id release-approval \
  --swarm payments \
  --work payment-release \
  --role product-owner \
  --to alternate-owner \
  --by primary-owner \
  --reason "The primary owner is unavailable for this release decision"

agora approval add \
  --swarm payments \
  --work payment-release \
  --role product-owner \
  --by alternate-owner \
  --delegation release-approval \
  --note "Accepted under delegated authority"
```

The record lives at
`.agora/swarms/<swarm>/work/<work>/approval-delegations/<id>/DELEGATION.md`. The approval row names
the delegated actor and delegation id. Consumption changes the record from `active` to `used`; it
cannot be replayed for another approval.

Only one active delegation may exist for a role on a work item. While it is active, Agora rejects a
direct approval by the assigned role holder. This prevents concurrent authorities from racing to
record the same role decision. Active delegations must also be consumed or revoked before the work
is completed or cancelled, or before the grantor's role is handed off.

## Revoke unused authority

Only the original grantor may revoke an active delegation:

```bash
agora approval delegation-revoke \
  --delegation release-approval \
  --swarm payments \
  --work payment-release \
  --by primary-owner \
  --reason "The primary owner resumed the decision"
```

A used or revoked delegation cannot be revoked or consumed again. Inspect the current records with:

```bash
agora approval delegations --swarm payments --work payment-release
agora approval delegations --swarm payments --work payment-release --status active
```

## Sign the lifecycle

Authenticated grantors prepare `approval.delegate`; authenticated delegated approvers prepare
`approval.add` with the delegation id. Authenticated grantors also prepare revocation:

```bash
agora approval delegate-prepare \
  --action-id grant-release-approval \
  --id release-approval \
  --swarm payments --work payment-release \
  --role product-owner --to alternate-owner --by primary-owner \
  --reason "Alternate review is required"

agora approval prepare \
  --id use-release-approval \
  --swarm payments --work payment-release \
  --role product-owner --by alternate-owner \
  --delegation release-approval --note "Accepted"

agora approval delegation-revoke-prepare \
  --action-id revoke-release-approval \
  --delegation release-approval \
  --swarm payments --work payment-release \
  --by primary-owner --reason "Delegation withdrawn"
```

Use `agora action authorization` and `agora action apply` for each prepared action. The signed grant
binds its target, role, work, and reason. A signed approval binds the delegation id and consumes that
exact record. A signed revocation binds the reason and active delegation state. Any intervening work
or delegation change invalidates the precondition digest.

## Customize a Method Pack

Grant both lifecycle actions only to roles that own delegable approval authority:

```yaml
allowed-actions: ["approval.add", "approval.delegate", "approval.delegation.revoke"]
```

Approval Delegation does not grant tool access, role assignment, transitions, Gate Waivers, or
authority over another work item. Environment-specific restrictions can further narrow whether the
resulting approval is sufficient for a deployment or external mutation.

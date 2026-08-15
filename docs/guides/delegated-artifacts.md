# Delegated artifact promotion

Agora can promote selected child artifact kinds into parent work when a delegation is collected.
Promotion is explicit in the original child contract and copies a typed durable reference, not the
artifact bytes or an opaque external file.

The child remains authoritative. This preserves provenance across repositories, cloud stores,
documentation systems, and agent environments without assuming that Agora can read or duplicate
their contents.

## Declare promotions

Use one `--promote-artifact source-kind=parent-kind` argument for each promised artifact:

```bash
agora delegation create \
  --id specialist-task \
  --swarm delivery \
  --work parent-slice \
  --to-actor specialist-swarm \
  --child-work child-slice \
  --title "Produce the specialist result" \
  --required-artifact child-result \
  --promote-artifact child-result=specialist-result \
  --by specialist-swarm
```

Every promoted source kind must also appear in `--required-artifact`. The child's terminal gate
therefore proves that the promised kind exists before collection. Source and target kinds are
validated slugs and the mapping is persisted as `artifact-promotions` in `DELEGATION.md`.

Authenticated proposals pass the same option to `delegation create-prepare`. The mapping is part of
the signed Lifecycle Action parameter map.

## Collection

Collection always records the existing whole-result reference:

```text
agora://swarms/<child-swarm>/work/<child-work>
```

For each promotion, Agora also adds the configured parent artifact kind with this reference:

```text
agora://swarms/<child-swarm>/work/<child-work>/artifacts/<source-kind>
```

The URI points to the child's `artifacts.md` record. Agora does not fetch the source URI, copy
repository files, rewrite cloud objects, or merge documents. A provider-specific transfer remains a
separate governed Tool Run whose resulting artifact can be recorded normally.

Collection fails when a promised source kind is absent, even if the child state was externally
corrupted to appear terminal. `agora validate` checks the source kind, promoted parent kind, and
exact reference for every collected delegation.

Run the [delegated work sample](../../samples/delegated-work/README.md) to inspect signed promotion
and collection.

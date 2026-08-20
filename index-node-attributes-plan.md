# `index` and `node` attributes: implementation plan

Working plan for closing devtools gap #2 (`dev3-migration-gaps.md`, `todo.md`) properly,
rather than continuing to stretch `pk`/`fk` to cover cases they don't fit. Context and full
reasoning live in conversation history; this doc is the standalone plan for implementation
and for handing off to flopy4.

## The core decision

`pk`/`fk` were being asked to answer two unrelated questions at once:

1. **Serialization**: does this integer need MF6's 1-based↔0-based translation on read/write?
2. **Relational identity**: does this column identify a row (`pk`), or point at one (`fk`)?

Evidence this conflation was already broken: flopy4 derives its `is_index`/`role="feature_id"`
conversion trigger from "`pk` or `fk` is set," then had to bolt on an `isinstance(col, Integer)`
guard after a `pk`/`fk` on a String field (MVR's `pname`) crashed `int()` — proof the vocabulary
was carrying a job it was never typed to carry safely.

Splitting into three orthogonal attributes:

- **`index`** — pure serialization fact. Doesn't claim uniqueness, doesn't claim to point
  anywhere.
- **`node`** — pure "this is a grid-cell reference" fact, resolved via DIS/DISV/DISU geometry
  at runtime, not via a schema `pk` lookup.
- **`pk`/`fk`** — unchanged shape, but now *only* mean relational identity (a value that
  identifies or points at a list row). No longer required to also signal serialization.

## `index: bool = False`

- Valid on: `Integer` scalars (anywhere — list-item column, record subfield, block field),
  and `Array` with `dtype: "integer"` (meaning: *the array's elements* are 1-based indices —
  covers `icvert`, `ja`, `irch`, `ievt`).
- **Not valid on `String`** — enforced by a schema validator, not just convention. This is the
  fix for the exact bug flopy4 patched around; the schema should guarantee it so nobody needs
  a defensive `isinstance` check downstream again.
- Migration: **direct copy** from v1's `numeric_index` wherever the field is `Integer` or
  `Array(dtype="integer")`. No heuristics, no block-name matching — same mechanical shape as
  the existing `layered`/`time_series` migration. String fields with v1 `numeric_index: true`
  (`utl-obs.id`/`id2`) get nothing, consistent with the existing conclusion that they're
  dynamic/non-numeric, not an oversight.

## `node: bool = False`

- Valid on: `Integer` scalars in list-item-column position (same placement `fk` currently
  requires).
- Meaning: this value is a grid-cell reference resolved from the parent model's grid at
  runtime — a structurally different resolution path than `fk` (geometry lookup, not
  pk lookup).
- Replaces the `fk="node"` sentinel. `fk` no longer accepts `"node"` as a value; it always
  means "resolves to a `pk` field," full stop. `schema.py`'s fk-structure validator loses its
  `fk == "node"` exemption branch and becomes a single-invariant check.
- Migration: **not** part of the direct/mechanical pass — same audit-as-you-go category as
  `pk`/`fk` backfill. Known corpus candidates: `exg-chfgwf`/`exg-gwegwe`/`exg-gwfgwf`/
  `exg-gwtgwt`/`exg-olfgwf`'s `cellidm1`/`cellidm2` (6 exchange types), `gwf-gnc`'s
  `cellidm`/`cellidn`.

## `pk`/`fk`: unchanged type, narrowed job (done, 2026-08-20)

No schema shape change to `pk`/`fk` themselves. `_resolve_relations`/`_mark_lonely_pk` keep
working as they did before. What actually landed, item by item from the original scan:

- **Lonely-pk allowlist extension** — `_LONELY_PK_FIELDS` widened to `vertices`, `cell2d`,
  `cell1d` (DISU/DISV/DISV1D/DISV2D's `iv`/`icell2d`/`icell1d`, 12 components). Genuinely the
  same shape `_mark_lonely_pk` already detects (leading required Integer, no fk, no existing
  pk) — no longer controversial now that `pk` doesn't need to "earn its keep" via a matching
  `fk`. On closer inspection, SFR's `diversions.iconr`, MAW's `connectiondata.icon`, and UZF's
  `packagedata.ivertcon` — originally bucketed here too — turned out **not** to fit this
  shape at all: none of them is the record's *leading* field (each follows an `ifno`/similar
  column that's already `pk`/`fk`'d), so `_mark_lonely_pk`'s single-field heuristic structurally
  can't reach them regardless of allowlist. Handled separately, below and under "compound-scoped
  fields."
- **Cross-component fk** — `idcxs`: defining side (`chf-cxs`/`olf-cxs`/`swf-cxs` packagedata,
  already `pk`'d) now referenced by `chf-cdb`/`chf-zdg`/`olf-zdg`/`swf-zdg` via
  `fk = "<component>.packagedata.idcxs"`. Required two fixes, not one: (1) the migration mapper
  needed a backfill pass, since `_resolve_relations` is single-component-scoped by construction;
  (2) `_validate_fk_fields` itself turned out to have a **latent bug** — despite `dfnspec.md`
  documenting `"[component.]block.field"` as a supported hierarchical form, the validator's
  `fk.split(".")[0]` only ever took the first dot-segment as the block name, so a real
  3-segment cross-component path like `"chf-cxs.packagedata.idcxs"` would have been
  misparsed as block name `"chf-cxs"` and rejected. Nobody had hit this before because nothing
  had ever actually set a cross-component `fk`. Fixed to resolve the target component via
  `spec.components` when 3 segments are present. `chf-dfw`/`olf-dfw`/`swf-dfw`'s `idcxs` is the
  same relation in principle but is an `Array` (a per-cell grid field, `shape=["nodes"]`), which
  cannot carry `fk` under the current schema at all (same limitation as item (a) below, never
  extended to `pk`/`fk`) — deliberately left alone, not an oversight.
- **Compound-scoped fields, now with an honest answer** — SFR `diversions.idv` gets `index`
  only (correctly — it's not globally unique, so it was never a valid `pk`). `diversions.iconr`
  gets `fk = "packagedata.ifno"` (a real reference into reaches) alongside `index`. UZF's
  `packagedata.ivertcon` turned out to be the same self-referential-fk shape (a UZF cell can
  point to another UZF cell in the same list) and got `fk = "packagedata.ifno"` too. MAW's
  `connectiondata.icon`, by contrast, has no real target at all — it's the same shape as
  `gwf-lak.iconn` (the field that originally motivated `index` in Phase 1): a per-parent
  connection sequence number, not globally unique, never referenced by name elsewhere. Correctly
  left with `index` only, no `pk`/`fk` — nothing to backfill there.

## Implementation steps (this repo)

1. **`schema.py`**: add `index: bool = False` to `Integer` and to `Array` (validator: only
   when `dtype == "integer"`); add `node: bool = False` to `Integer`; remove `"node"` from
   `fk`'s accepted forms; simplify the fk-structure validator (drop the `node` exemption).
2. **`dfnspec.md`**: document `index` under Integer and Array type-specific attributes;
   document `node` under Integer; rewrite the "Primary and foreign keys" section's "Grid cell
   sentinel" form out, replacing it with a description of `node` as a distinct attribute.
3. **`schema.json`**: regenerate for the new attributes. (Note: this file was already stale
   before this work — missing `removed`/`deprecated`/`layered` on `Array` — so full
   regeneration will surface that unrelated drift too; reconcile it in the same pass rather
   than hand-editing around it again.)
4. **`migrate_to_v2_0_0_dev2.py`** (or wherever the per-field mapper lives):
   - Direct `index` migration: for `Integer` fields and `Array(dtype="integer")` fields,
     `index = try_parse_bool(f.get("numeric_index"), False)`.
   - New `_mark_node_refs`-style pass, audited per field, for the exchange `cellidm1`/
     `cellidm2` and GNC `cellidm`/`cellidn` cases.
5. `pk`/`fk` extensions (separate, lower-priority commits, any order): lonely-pk allowlist
   widening; cross-component `idcxs` pass; SFR `diversions` fk/index split.
6. Update `todo.md` to replace the (a)–(g) bucket list with these concrete, independently
   trackable items.
7. Full `autotest/dfns/` suite + snapshot regeneration after each step.

## What flopy4 needs to change (separate repo, coordinate before/alongside)

- Switch `is_index`/`role="feature_id"` derivation from "`pk` or `fk` is set, Integer-only" to
  reading `index` directly. Drop the defensive `isinstance(col, Integer)` patch — no longer
  needed, the schema enforces it now.
- If/when typed grid-cell references are wanted (the deferred "Union-item-class shape" work),
  consume `node` instead of checking `fk == "node"`.
- No urgency on the `pk`/`fk` backfill items above — those remain best-effort relational
  documentation, not something flopy4 should block on.

## Sequencing

- **Phase 1 (done, 2026-08-20)**: `index` — schema + validator + direct migration. This is
  the piece that actually unblocks flopy4 and closes gap #2's practical urgency. Small,
  mechanical, low-risk. Landed: `Integer.index`/`Array.index` in `schema.py` (validator bars
  `index=True` off `dtype != "integer"` Arrays; `String` never gets the field at all),
  `dfnspec.md` documented, `schema.json` regenerated (also picked up pre-existing unrelated
  drift — `removed`/`deprecated`/`layered` on `Array` — as anticipated above),
  `migrate_to_v2_0_0_dev2.py` populates `index` directly from v1 `numeric_index` for every
  `Integer`/`Array(dtype="integer")` field. Confirmed fixes the `gwf-lak.iconn` regression
  from `todo.md`. Full `autotest/dfns/` suite green; snapshots regenerated (306 files,
  additive-only diff — every change is a bare `"index": true`/`index = true` addition, no
  removals beyond JSON trailing-comma churn).
- **Phase 2 (done, 2026-08-20)**: `node` — schema + validator + `fk="node"` removal + the
  handful of exchange/GNC backfills. Well-scoped enough to go in the same pass as Phase 1.
  Landed: `Integer.node` in `schema.py` (no placement validator — same as `pk`/`fk`, this is
  a documentation-level convention, not schema-enforced); `_validate_fk_fields`'s `fk == "node"`
  exemption removed, now a single hierarchical-path-vs-fk_ref invariant check (an unqualified
  `fk = "node"` is no longer special — it must resolve to an actual list block like any other
  bare fk value, which in practice means nobody will set it, achieving the deprecation without
  a hard reject); `dfnspec.md` updated (`node` documented under Integer, "Primary and foreign
  keys" section's grid-cell-sentinel form replaced with a pointer to `node`); `schema.json`
  regenerated; a new `_mark_node_refs` pass in `migrate_to_v2_0_0_dev2.py` backfills the 6
  corpus candidates by an explicit per-component allowlist (`_NODE_REF_FIELDS`) — the 5
  exchange types' `exchangedata.cellidm1`/`cellidm2` and `gwf-gnc.gncdata.cellidm`/`cellidn` —
  since (unlike `index`) v1 has no attribute this can be migrated from mechanically.
  `autotest/dfns/test_schema_relations.py`'s node-sentinel-specific test was replaced with one
  asserting the new (unremarkable) behavior. Full `autotest/dfns/` suite green; snapshots
  regenerated (36 files, additive-only — 6 components x 2 fields x 2 dev dirs x 3 formats).
- **Phase 3 (done, 2026-08-20)**: `pk`/`fk` extensions — lonely-pk allowlist widened
  (`_LONELY_PK_FIELDS` in `migrate_to_v2_0_0_dev2.py`); a new `_apply_fk_backfill` pass (keyed
  on an explicit `_FK_BACKFILL` allowlist, same shape as Phase 2's `_mark_node_refs`) sets `fk`
  for UZF's `ivertcon`, SFR's `iconr`, and the 4 cross-component `idcxs` referencing fields;
  `_validate_fk_fields`'s cross-component path resolution bug fixed (see above) — a real latent
  defect, not something this plan anticipated, found only by actually exercising the documented
  3-segment form for the first time. MAW's `connectiondata.icon` and the 3 `*-dfw` components'
  `idcxs` (an `Array`, can't carry `fk`) investigated and deliberately left alone, documented
  above rather than silently skipped. Full `autotest/dfns/` suite green; snapshots regenerated
  (108 files, additive-only — exactly 12×2 lonely-pk + 1 UZF + 1 SFR + 4 cross-component,
  ×2 dev dirs ×3 formats).

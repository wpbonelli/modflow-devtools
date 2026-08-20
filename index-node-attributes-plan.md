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

## `pk`/`fk`: unchanged type, narrowed job

No schema shape change. `_resolve_relations`/`_mark_lonely_pk` keep working as they do today.
The difference is priority: this is no longer blocking anything (flopy4's conversion need is
served by `index`), so it becomes incremental, best-effort relational-documentation work.
Corpus-identified remaining items, from the earlier scan, each independently schedulable:

- **Lonely-pk allowlist extension** — same shape `_mark_lonely_pk` already detects, just
  outside `_LONELY_PK_FIELDS`: DISU/DISV/DISV1D's `vertices.iv`, `cell2d.icell2d`,
  `cell1d.icell1d`; SFR's `diversions.iconr`; MAW's `connectiondata.icon`; UZF's
  `packagedata.ivertcon`. No longer controversial for DISU/DISV now that `pk` doesn't need to
  "earn its keep" via a matching `fk` — marking it is just honestly documenting a real,
  if unreferenced, row identifier.
- **Cross-component fk** — `idcxs`: defining side (`chf-cxs`/`olf-cxs`/`swf-cxs`) already
  `pk`'d; referencing side (`chf-dfw`, `chf-cdb`, `chf-zdg`, `olf-dfw`, `olf-zdg`, `swf-dfw`,
  `swf-zdg`) needs `fk`. Requires a pass that can see across component boundaries —
  `_resolve_relations` currently can't.
- **Compound-scoped fields, now with an honest answer** — SFR `diversions.idv` gets `index`
  only (correctly — it's not globally unique, so it was never a valid `pk`). `diversions.iconr`
  gets `fk = "packagedata.ifno"` (a real reference into reaches) alongside `index`.

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
- **Phase 2 (now, small)**: `node` — schema + validator + `fk="node"` removal + the handful of
  exchange/GNC backfills. Well-scoped enough to go in the same pass as Phase 1.
- **Phase 3 (later, incremental, no urgency)**: `pk`/`fk` extensions — lonely-pk allowlist,
  cross-component `idcxs`, SFR `diversions` split.

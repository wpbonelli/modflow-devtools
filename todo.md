# Done

- block.optional derived from fields (any required field → mandatory; all optional → optional)
- block repetition × optionality interaction clarified in spec (2×2 matrix)
- self-sizing arrays: position-based rules replace string-specific rules
  - self-sizing (shape=[]) valid at top level and as rightmost record subfield
  - non-rightmost record subfield with no shape is a validation error
  - any dtype, not just string
- array dimension attribute: valid on any self-sizing array (not string-only)
  - dimension sources provide dynamic element count to other arrays' shape expressions
- schema version consistency validated across components in a DfnSpec
- bound-annotated shape expressions (<, >, <=, >=) parsed and validated
- intra-record sibling scope restricted to Integer (Array.dimension="record" removed)
- dfnspec.md updated throughout to reflect all of the above

# Todo

## v1 → v2 mapper gaps (now visible from TOML output)

- [x] period blocks should have `repeats: true` — mapper never sets this on any block
- [x] `auxiliary` (and similar self-sizing string arrays that define a named set) should have
  `dimension: "component"` set by the mapper — the v1 DFN shape `(naux)` is the signal
  that the array's length defines a dimension used elsewhere
- [x] `model_dump(exclude_none=True)` serializes False boolean defaults verbosely
  (developmode, netcdf, time_series, pk, etc.) — replaced with `_to_toml_dict` which
  introspects `field_info.default is False` to suppress them without hardcoding names
- [x] single-file v2 conversion in dfn2toml.py skips the v1→v2 mapping step (passes raw
  Dfn dataclass to _convert instead of a mapped Component)
- [x] period block list structure: `map_period_block` removed; recarray List structure
  preserved as-is from v1 → v2 mapping
- [x] `repeats: true` now derived from `block_variable` attribute on v1 FieldV1 (not
  hardcoded to "period"); `solutiongroup` in sim-nam correctly gets `repeats: true`
- [x] arithmetic shape elements (`dim [+-] integer`, e.g. `nseg-1`) added to validator
- stress period list fields should be explicitly marked optional or not in the mapper
  (most are optional but some are required)

## v1 → v2 migration gaps found during flopy4 dev3 migration (2026-08-18)

- [x] `Array.repeat` was never populated by migration, and turned out not to be needed:
  removed instead of fixed. History (see git log on `modflow_devtools/dfns/schema.py`):
  pre-#311, the v1→v2 mapping was a loose passthrough (raw v1 field dict, lightly sorted),
  so v1's `repeating: true` survived into dev0/dev1 output automatically with no dedicated
  code. #311's schema rewrite switched to a strict, fully-typed schema and redesigned
  `repeating: bool` into `repeat: str | None` (a reference, not a flag) — but nothing was
  ever written to populate it, and `dfnspec.md`'s promised elaboration ("See `repeat`
  section below") was a dangling link, then and now. Checked what the 3 real fields with
  v1 `repeating true` (`utl-tas.tas_array`, `prt-oc.times`, `prt-prp.times`) would even
  reference: all 3 also have v1 `shape (any1d)`, which the mapper already collapses to
  `shape=[]` (self-sizing) — matching `dfnspec.md`'s existing self-sizing-array semantics
  exactly (MF6 reads values until it runs out). None has a sibling field to point to as a
  count source, so the reference design never matched real data. Removed `Array.repeat`
  from `schema.py`, `dfnspec.md`, and `schema.json` rather than backfilling a migration for
  a field nothing consumes and no data supports.

- Confirmed *not* a gap, for the record: worried `rtype` (OC `saverecord`/`printrecord`
  arms) might not have its valid-value set migrated into `String.valid`, which would have
  meant flopy4 couldn't drop its hardcoded `_OC_RTYPES` table. Checked directly —
  `rtype.valid` is populated correctly per component (`['HEAD', 'BUDGET']` for gwf-oc,
  etc.), sourced from the v1 DFN description text. No migration work needed here.

- [x] **`numeric_index` → `pk`/`fk` backfill (a838d84, #337) covered fewer fields than the
  v1 corpus actually has flagged.** That fix targeted 6 fields (BUY/CSUB/VSC/PRP/ATS/CXS
  self-referential primary keys). A full corpus scan (walking v1 DFNs recursively including
  list/record children, matched by field name against dev3's fully-recursed leaf fields —
  a flat top-level-only scan finds 0, since most of these live inside `List.item.fields`,
  not directly in `Block.fields`) turns up **44** fields with v1 `numeric_index: true` and
  no `pk`/`fk` in dev3. Confirmed one causes a real behavioral regression, not just a
  metadata gap: `gwf-lak.iconn` (connectiondata's per-lake connection sequence number) needs
  the same 0-based-Python/1-based-file conversion `pk`/`fk` columns get; without it, MF6
  rejects the written file (`iconn FOR LAKE 1 MUST BE > 1 and <= 9`) — confirmed by
  reproducing the failure, then fixing it with a local flopy4-side `pk = true` override,
  which resolved it. flopy4 has only patched `iconn` so far (the one confirmed to break a
  real test); the other 43 are unaudited case-by-case but are almost certainly the same
  category — most are named like connection/vertex/cell sequence numbers scoped *within* a
  parent row rather than unique across their whole table (`icell1d`/`icell2d`/`iv`
  (DISU/DISV vertex indices), `icon`/`iconr`/`idv` (MAW/SFR connection numbers, siblings of
  `iconn`), `cellidm1`/`cellidm2`/`cellidm`/`cellidn` (exchange cellid refs), `idcxs`
  (cross-section id ref), `bndno` (SPC)) — plus `gwf-mvr.id1`/`id2`, which the flopy4-side
  corpus audit (namefile-load-plan.md, Phase 0.6a) already separately concluded are
  genuinely dynamic/untyped (target package resolved by name at runtime, not a formal FK) so
  may not need a schema change at all, just confirmation that `index=True`-equivalent
  handling is enough on the consumer side. Given the pattern (numeric_index true, not a
  pk/fk match) is the same root cause already identified for the 6-field fix, this reads
  like the fix's structural-signal net needs to be wider (or a distinct
  "index but not a full pk" concept needs a name), not a new bug — flagging so the full 44
  get audited under the same pass rather than trickling in one flopy4 regression at a time.
  Resolved by decomposing `pk`/`fk`'s conflated "needs 1-based/0-based conversion" +
  "is a relational key" concerns into a dedicated `index` attribute — see
  `index-node-attributes-plan.md`, Phase 1: added `Integer.index`/`Array.index` (the latter
  gated to `dtype == "integer"` by a validator, and never valid on `String`), and a direct
  mechanical migration (`index = numeric_index` for every `Integer`/`Array(dtype="integer")`
  field) in `migrate_to_v2_0_0_dev2.py`. This is a superset of the 44-field gap: it applies
  unconditionally alongside any existing `pk`/`fk`, not just where those are absent, and
  fixes the confirmed `gwf-lak.iconn` regression directly (`index=True` now set on that
  field). `schema.json`/`dfnspec.md` updated; full `autotest/dfns/` snapshot suite
  regenerated (306 files, additive-only diff). Phase 2 (`node` attribute, replacing the
  `fk="node"` sentinel) also done — see (e) below. Phase 3 (`pk`/`fk` backfill) also done — see
  (b)/(d)/(f) below. All decomposed sub-issues (a)–(g) resolved; full detail in
  `index-node-attributes-plan.md`.

- [x] **Bare (valueless) boolean attribute lines in v1 DFNs migrated as `False` instead of
  `True`.** v1 syntax allows a boolean attribute's line to carry no value at all (e.g. a
  bare `optional` line, vs. `optional true`/`optional false`), meaning the attribute is set.
  `load_dfn` parses such a line to `""` (as opposed to `None` for a wholly absent attribute),
  but `try_parse_bool("", default)` unconditionally returned `False` regardless of `default`,
  silently inverting the flag. Not `optional`-specific: any boolean attribute using this v1
  convention was affected (confirmed `tagged` also uses bare lines in the real corpus, 23
  occurrences across 18 files, though none happened to change rendered output this pass).
  Fixed at the root in `try_parse_bool` (`modflow_devtools/misc.py`) rather than patching call
  sites individually. Real-corpus impact turned out wider than originally scoped: beyond the
  6 known `*-oc`/`gwt-ist` printrecord files, `chf-dfw`, `chf-disv1d`, `gwf-npf`, `olf-dfw`,
  `olf-disv1d`, `swf-dfw`, `swf-disv1d`, and `sim-nam` also had real bare-`optional` fields
  that are now correctly migrated as optional. One existing test
  (`test_render_respects_tagged_scalars_in_record`) had baked in the old (buggy) rendering of
  `gwf-oc`'s `columns`/`width`/`digits` as required; updated to expect them bracketed as
  optional, matching flopy4's independently-confirmed real MF6 behavior for the same fields.

- Gap #2 (`numeric_index` → `pk`/`fk`, above) decomposed into concrete sub-issues after a
  recursive scan against the real corpus (52 components, 98 `numeric_index: true`
  occurrences). Not one bug — five different things producing the same symptom:
  - [x] **(c) `_LONELY_PK_BLOCKS`/`_mark_lonely_pk` matched on the wrong name.** MF6's
    convention is block `period` + list field `perioddata` (never the same string), so the
    `"perioddata"` entry in the allowlist could never match *any* component — dead since
    a838d84. Fixed by matching on the list field's own name instead of the enclosing block's
    (`_LONELY_PK_FIELDS`, `migrate_to_v2_0_0_dev2.py`). Caught `utl-spc.bndno`. Also had to
    move `_mark_lonely_pk`'s call to *after* `_fix_lak_relations`/`_fix_mvr_relations` in the
    pipeline: LAK's period `number` field (the deliberately-ambiguous lake-or-outlet field —
    see `_fix_lak_relations`'s docstring) structurally looks exactly like a lonely pk before
    `_fix_lak_relations` splits it into per-arm `lakeno`/`outletno` fk's; marking it pk first
    leaked a stale `pk=True` into those fk copies via `model_copy`. Full suite green after the
    reorder, only `bndno` changed.
  - [x] **(b) Same lonely-pk shape, blocked by a hardcoded name allowlist.** DISU/DISV/DISV1D's
    `vertices.iv`, `cell2d.icell2d`, `cell1d.icell1d` (24 occurrences), SFR's
    `diversions.iconr`/`idv`, MAW's `connectiondata.icon`, UZF's `packagedata.ivertcon` are the
    same shape `_mark_lonely_pk` already detects, just under block/field names outside
    `_LONELY_PK_FIELDS`. The DISU/DISV case is a deliberate exclusion in the current docstring
    ("a distinct grid-geometry concern") — open question: is `pk=true` still correct/useful
    there even though nothing can carry a matching `fk` back (the only things that reference
    vertex/cell numbers, e.g. `icvert`, are Arrays, which can't hold `fk` at all per (a))?
    Resolved (Phase 3, `index-node-attributes-plan.md`): yes, `pk=true` is still correct/useful
    there — it's an honest, if unreferenced, row identifier, same as several `_LONELY_PK_FIELDS`
    entries already are. `_LONELY_PK_FIELDS` widened to `vertices`/`cell2d`/`cell1d` (12
    components). The other three named here — SFR `iconr`, MAW `icon`, UZF `ivertcon` — turned
    out on inspection *not* to be this shape at all (none is the record's leading field, so
    `_mark_lonely_pk` structurally can't reach them regardless of allowlist); resolved instead
    under (f) and via a new `_apply_fk_backfill` pass, see below.
  - [x] **(d) Cross-component FKs unreachable by construction.** `idcxs`: defining side
    (`chf-cxs`/`olf-cxs`/`swf-cxs`) already `pk`'d; referencing side (`chf-dfw`, `chf-cdb`,
    `chf-zdg`, `olf-dfw`, `olf-zdg`, `swf-dfw`, `swf-zdg`) never gets `fk` set, because
    `_resolve_relations` only ever sees one component's own `blocks` dict. Schema already
    supports this (`fk = "[component.]block.field"`); migration mapper never attempts it.
    Resolved (Phase 3): new `_apply_fk_backfill` pass sets
    `fk = "<component>.packagedata.idcxs"` on the 4 referencing fields that are actually Integer
    list columns (`chf-cdb`, `chf-zdg`, `olf-zdg`, `swf-zdg`). Turned up a second, deeper bug
    while doing this: `_validate_fk_fields` itself mishandled the 3-segment
    `"component.block.field"` form (`fk.split(".")[0]` only ever took the first segment as the
    block name, so it would've rejected exactly this case) — nobody had hit it before because
    no `fk` had ever actually used the cross-component form. Fixed to resolve via
    `spec.components`. `chf-dfw`/`olf-dfw`/`swf-dfw`'s `idcxs` is the same relation in principle
    but is an `Array` (`shape=["nodes"]`) — initially left alone since `Array` couldn't carry
    `fk` at all, then resolved in a follow-up pass the same day: added `Array.fk` (dtype=
    "integer" only; no `pk`/`fk_ref` counterpart — an array has no rows of its own to key, and
    no sibling record for a runtime component selector), which `_validate_fk_fields` already
    validates for free via its `getattr`-based field walk. Backfilled via a new
    `_apply_array_fk_backfill` pass (`_ARRAY_FK_BACKFILL` allowlist) on all 3 `*-dfw`
    components. MAW's `connectiondata.icon` (below, under (f)) reconfirmed as permanently out
    of scope in the same pass — not a parallel gap, just double-checked.
  - [x] **(e) `fk = "node"` grid-cell sentinel, unused.** `exg-*.cellidm1`/`cellidm2` (6
    exchange types), `gwf-gnc.cellidm`/`cellidn` look like the schema's existing grid-cell
    sentinel case, already speced and validated in `schema.py`, never populated by the mapper.
    Resolved by replacing the sentinel entirely with a dedicated `Integer.node` attribute
    (Phase 2, `index-node-attributes-plan.md`): confirmed the actual corpus count is 5
    exchange components (`exg-chfgwf`/`exg-gwegwe`/`exg-gwfgwf`/`exg-gwtgwt`/`exg-olfgwf`, each
    with `exchangedata.cellidm1`/`cellidm2`) plus `gwf-gnc.gncdata.cellidm`/`cellidn` — 6 fields
    total across those, not "6 exchange types" as the original note implied. Backfilled by a
    new `_mark_node_refs` pass keyed on an explicit `_NODE_REF_FIELDS` allowlist (audited, not
    derived — v1 has no attribute this maps from). `fk = "node"` itself is no longer a special
    sentinel: `_validate_fk_fields` dropped its exemption, so an unqualified `fk = "node"` now
    just has to resolve to an actual list block like any other bare fk value (in practice
    meaning nobody sets it — the deprecation is structural, not a hard reject).
  - [x] **(a) Array-typed fields can't take `pk`/`fk` at all.** `irch`, `ievt`, `icvert`, `ja`,
    `ic`, `cellidsj` are `Array`s; `dfnspec.md` restricts `pk`/`fk` to integer/string columns
    in a list item record. v1's `numeric_index` on these likely just means "apply 1-based
    conversion," a concept with no home in v2 outside the relational `pk`/`fk` vocabulary.
    Resolved: `numeric_index` never meant relational identity here, so it doesn't need
    `pk`/`fk` — it needed `Array.index` (Phase 1, `index-node-attributes-plan.md`), now
    migrated directly for every `Array(dtype="integer")` field.
  - [x] **(f) Compound keys — no concept for them.** SFR's `diversions.iconr`/`idv` are unique
    only per-reach, not table-wide; a blind `pk=true` would misrepresent them. `pk`/`fk` as
    specced has no compound-key notion. Resolved (Phase 3): no new concept needed once `pk`/`fk`
    aren't asked to double as the serialization signal — `idv` correctly gets `index` only (from
    Phase 1, mechanically; it was never a valid `pk`, compound-scoped or not). `iconr` isn't
    compound-scoped at all on inspection — its description ("the downstream reach that will
    receive the diverted water") makes it a real, globally-scoped reference into
    `packagedata.ifno` (reach numbers), so it gets `fk = "packagedata.ifno"` via
    `_apply_fk_backfill`, same as any other single-column fk. UZF's `packagedata.ivertcon`
    (self-referential: a UZF cell may point to another UZF cell below it) turned out to be the
    same single-column-fk shape and got the same treatment. MAW's `connectiondata.icon` is the
    one genuine compound-scoped case with no real target (same shape as `gwf-lak.iconn`) —
    correctly left with `index` only, nothing more to add.
  - [x] **(g) `gwf-mvr.id1`/`id2`, `utl-obs.id`/`id2`** — already independently audited
    (dynamic/name-resolved, not a formal FK). Confirmed by this scan too; no work needed.

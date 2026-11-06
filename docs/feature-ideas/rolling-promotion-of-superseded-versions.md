# Feature idea: rolling promotion of superseded versions

**Status:** idea — to be investigated
**Component:** `WorkSpaceOneAssigner`
**Origin:** observed while testing the pruner safeguard against a production WS1 UEM tenant
(equinor/autopkg-cicd dev-work notes 054 and 055, 2026-11-06)

## Problem

`WorkSpaceOneAssigner` applies the staged assignment rules (e.g. TESTING → QA → PROD with
`distr_delay_days`) **only to the latest version** found on WS1. A version therefore reaches a later
stage only if no newer release appears before that stage's delay has elapsed — effectively
`delay + 1` days, since a daily run can miss release day.

For fast-moving apps this means later stages are rarely reached at all. Observed for
Microsoft Visual Studio Code (≈1.8 releases/week, PROD delay 7 days):

- 15 versions over 58 days; time each spent as "latest": `1, 6, 8, 4, 3, 7, 6, 1, 7, 1, 6, 5, 1, 2` days
- only **one** version (8 days as latest) reached PROD in ~7 weeks
- PROD stayed pinned to that version (433 assigned devices) while 12 newer versions piled up at
  TESTING/QA
- the pruner's `ws1_app_versions_to_keep` had to be raised to 12 just to keep the PROD version
  inside the keep window; the pruning safeguard was the only thing preventing its deletion

Operators are currently forced to trade soak time against release cadence: a shorter PROD delay
lets more versions through but reduces soak; a longer keep count masks the stall but costs storage
and clutter.

## Proposed behaviour

Decouple *soak time* from *being the latest version*:

> For each stage S with delay D, promote the **newest version whose first (TESTING) assignment is
> at least D days old and that is newer than the version currently at stage S** — not only the
> latest version overall.

Equivalent formulation: a version is eligible for stage S once it has soaked ≥ D days; among eligible
versions, pick the newest; apply S to it if it is newer than the current holder of S.

Effects:

- Soak time becomes a true minimum age, independent of how often new releases land.
- Every stage is guaranteed to advance within `D + release interval` days.
- Keep count can be reasoned about as `(#stages) + buffer` rather than "long enough to cover the
  worst stall".
- Behaviour for slow-moving apps is unchanged (the newest eligible version *is* the latest).

## Design notes / open questions

1. **Where does "first assignment date" come from?** The pruner already derives day0 from
   `assignments[0].distribution.effective_date` via `/api/mam/apps/{uuid}/assignment-rules` (v2).
   The assigner can reuse the same lookup for every macOS version of the app, not just the latest.
2. **Skipping intermediate versions.** If versions A < B < C exist and both B and C are eligible for
   PROD, promote C only. B never gets PROD — it should then be a prune candidate (0 assigned), which
   is the desired outcome.
3. **Only Autopkg-tagged rules.** Keep the existing guard: only touch assignment rules whose
   description carries the `#AUTOPKG` tag, so manually curated assignments are not overridden.
4. **Future `effective_date` caveat.** The existing NB in `WorkSpaceOneAssigner` still applies — a
   rule with a future `effective_date` blocks older versions from deploying, so rules must still be
   written only when their date has arrived.
5. **Interaction with `auto_update_devices_with_previous_versions` /
   `keep_app_updated_automatically`.** Unchanged, but worth confirming in testing that devices on
   the old PROD version move to the new one as expected.
6. **Opt-in.** Introduce as a new input (e.g. `ws1_assign_rolling_promotion: 'True'|'False'`, default
   `False`) so existing behaviour is preserved until operators opt in.
7. **Testing.** Unit-test the selection function with synthetic version/date sets covering: no
   eligible version, one eligible, several eligible with gaps, eligible version older than current
   holder. Acceptance test against a tenant with a fast-moving app (VS Code, Chrome, Edge).
8. **Console-created rules may carry a back-dated `effective_date`.** Observed 2026-11-06: an
   operator manually added a PROD assignment to VS Code 1.143.1 in the WS1 UEM console (CET, late
   morning); the API returned `effective_date: 2026-11-05T00:00:00` — the previous calendar day,
   most likely the console storing the date in UTC and/or truncating the time. Implications:
   - Day0 derived from `assignments[0].distribution.effective_date` can be up to a day earlier
     than the real import for manually created rules; eligibility checks should treat
     `effective_date` as date-only and tolerate ±1 day rather than comparing to "today" exactly.
   - When the assigner writes its own rules it already uses a date-only ISO string, so dates it
     produces are unaffected — but mixed manual/automatic histories will show this skew.
   - Manual promotions are a legitimate operator action (the interim mitigation above relied on
     one). The selection rule must treat a manually assigned stage holder exactly like an
     automatic one: never re-pin a stage to an older version, only supersede with a newer one.

## Interim mitigation (in use at Equinor)

Shorter delays and a smaller keep count tuned to the observed cadence — VS Code: QA 3→2, PROD 7→4,
keep 12→8 — with the pruning safeguard (`ws1_prune_safeguard_halt_on_assigned: 'False'`) as the
backstop that skips and Slack-notifies rather than deleting an assigned version.

## Related

- `ws1_prune_safeguard_halt_on_assigned` / `ws1_prune_safeguard_triggered` (pruner safeguard)
- Operator note: the WS1 console's "assigned devices" count lags behind the API; the API's
  `AssignedDeviceCount` is authoritative for both the assigner and the pruner.

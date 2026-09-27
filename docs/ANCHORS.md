# Mathematical anchors

Sanitized extraction of symbolic derivations accompanying the source harness. The original author described these as manually derived. That historical chronology has not been independently verified here; this extraction is not a new independence attestation or human approval. Numerical values are retained and tested against the separate oracle and reference.

### Numerical representation and tolerance

All anchors are exact rationals. The oracle computes in `fractions.Fraction`,
so the frozen comparison is **exact rational equality**, tolerance `0`. Where a
component is compared after conversion to IEEE-754 double (reference target,
black-box JSON responses), the permitted tolerance is `1e-12` absolute. No
anchor below has a value whose correctness depends on a looser tolerance; the
`1e-12` allowance exists only to absorb JSON float round-tripping.

### Notation

Categories are `1..10`, higher is better. For independent draws `X ~ p` and
`Y ~ q` on those categories:

- `W = P(X > Y)`, `L = P(X < Y)`, `T = P(X = Y)`;
- `PS(X,Y) = W + 0.5 T`;
- `h(a,b) = 1` if `a > b`, `0.5` if `a = b`, `0` if `a < b`, so
  `PS = sum_a sum_b p_a q_b h(a,b)`;
- Cliff's delta `= 2 PS - 1`.

Cells are `00`, `A0`, `0B`, `AB`; `P0 = PS(Y_00, Y_0B)`,
`PA = PS(Y_A0, Y_AB)`, `I_P = P0 - PA`. Frozen thresholds: `T_B^P = 0.20`
(so the C1 boundary is `P0 >= 0.70`), `M_I^P = 0.15`, `E_B^P = E_I^P = 0.05`,
`M_C = 0.10`, `E_C = 0.05`.

---

## A01 — All comparisons tied

**Claim.** If `X` and `Y` are identical point masses at the same category `c`,
then `W = 0`, `L = 0`, `T = 1`, `PS = 0.5`, `delta = 0`.

**Derivation.** `p_c = 1` and `q_c = 1`, all other masses zero. The only
non-vanishing term in `sum_a sum_b p_a q_b h(a,b)` is `a = b = c`, contributing
`1 * 1 * h(c,c) = 0.5`. Separately `W = P(X > Y) = sum_{a > b} p_a q_b = 0`
because the only occupied pair has `a = b`; identically `L = 0`; and
`T = p_c q_c = 1`. Hence `PS = W + 0.5 T = 0 + 0.5 = 1/2` and
`delta = 2(1/2) - 1 = 0`.

**Anchor values.** `W = 0`, `L = 0`, `T = 1`, `PS = 1/2`, `delta = 0`.

This holds for every `c in {1,...,10}`; the frozen fixture uses `c = 1`
(floor), `c = 5` (interior) and `c = 10` (ceiling) to confirm that the value is
category-independent.

---

## A02 — Complement identity

**Claim.** `PS(X,Y) + PS(Y,X) = 1` for any `p`, `q`.

**Derivation.** Write `W = W(X,Y) = P(X > Y)` and `L = L(X,Y) = P(X < Y)`. By
definition `W(Y,X) = P(Y > X) = P(X < Y) = L` and `T(Y,X) = P(Y = X) = T`.
Therefore

```
PS(X,Y) + PS(Y,X) = (W + 0.5 T) + (L + 0.5 T)
                  = W + L + T
                  = 1,
```

the last equality because `{X > Y}`, `{X < Y}`, `{X = Y}` partition the sample
space of the independent pair. The identity is unconditional: it does not
require continuity, tie-freeness, or equal support.

**Anchor value.** `PS(X,Y) + PS(Y,X) = 1` exactly, for every fixture pair in
the panel.

---

## A03 — Win/loss/tie decomposition sums to one

**Claim.** `W + L + T = 1`, and `PS = W + 0.5 T` is therefore equivalent to
`PS = (1 + W - L)/2`.

**Derivation.** The three events partition the space, giving `W + L + T = 1`.
Substituting `T = 1 - W - L` into `PS = W + 0.5T` yields
`PS = W + 0.5 - 0.5W - 0.5L = 0.5 + 0.5(W - L) = (1 + W - L)/2`.

**Anchor value.** `W + L + T = 1` exactly; `2 PS - 1 = W - L` exactly.

---

## A04 — Cliff-scale transform identity

**Claim.** `delta = 2 PS - 1 = W - L`, and the interaction transforms as
`I_delta = delta0 - deltaA = 2 I_P`.

**Derivation.** From A03, `2 PS - 1 = W - L`, which is exactly Cliff's delta in
its standard `P(X>Y) - P(X<Y)` form. Hence the registered transformation
`delta = 2 PS - 1` is not a second estimator but the same functional on a
rescaled axis. For the interaction,

```
I_delta = delta0 - deltaA = (2 P0 - 1) - (2 PA - 1) = 2 (P0 - PA) = 2 I_P.
```

**Consequences fixed as anchors.** The registered boundary images are exact:
`P0 = 0.70  <->  delta0 = 2(0.70) - 1 = 0.40`;
`I_P = 0.15  <->  I_delta = 0.30`;
equivalence half-width `0.05` on the `PS` scale maps to `0.10` on the Cliff
scale; the `PS` equivalence region `[0.45, 0.55]` maps to `[-0.10, +0.10]`.

**Anchor values.** `delta(PS=1/2) = 0`; `delta(PS=7/10) = 2/5`;
`I_delta(I_P=3/20) = 3/10`; `K_A^delta = 2 K_A - 1 = 1 - p_floor,A0` (A08).

---

## A05 — Complete separation and complete reverse separation

**Claim (separation).** `X` point mass at `10`, `Y` point mass at `1`:
`W = 1`, `L = 0`, `T = 0`, `PS = 1`, `delta = 1`.

**Derivation.** The single occupied pair is `(a,b) = (10,1)` with `a > b`, so
`h = 1` and `PS = 1 * 1 * 1 = 1`. `T = 0` because no category carries mass in
both distributions; `L = 0` because no occupied pair has `a < b`.

**Claim (reverse separation).** `X` point mass at `1`, `Y` point mass at `10`:
`W = 0`, `L = 1`, `T = 0`, `PS = 0`, `delta = -1`.

**Derivation.** The single occupied pair is `(1,10)` with `a < b`, so `h = 0`
and `PS = 0`. By A02 the two cases are complements: `1 + 0 = 1`.

Separation is not restricted to the extreme categories: any `X` supported
strictly above the support of `Y` gives `PS = 1`. The frozen panel includes
`X` at `3`, `Y` at `2` to prove that `PS = 1` does not require maximal
category distance — the estimand is ordinal, not metric.

**Anchor values.** `PS = 1` and `PS = 0` with the stated `W/L/T` triplets.

---

## A06 — Unbiased within-cell collision probability

**Claim.** For realized counts `n_1..n_10` with `n = sum_k n_k > 1`, the
registered estimator is `C_hat = sum_k n_k (n_k - 1) / [n (n - 1)]`.

**Derivation.** Draw two *distinct* calls from the cell without replacement.
The number of ordered distinct pairs is `n(n-1)`. The number of ordered
distinct pairs whose two calls both fall in category `k` is `n_k(n_k - 1)`.
Summing over the ten mutually exclusive categories and dividing gives the
proportion of distinct ordered pairs that collide,

```
C_hat = sum_k n_k(n_k - 1) / [n(n - 1)].
```

**Unbiasedness.** For i.i.d. draws from `p`, `E[n_k(n_k-1)] = n(n-1) p_k^2`, so
`E[C_hat] = sum_k p_k^2 = C`. The self-pair exclusion is exactly what removes
the `+1/n` bias of the naive plug-in.

**Anchor value.** The estimator formula itself, plus A07 and A09 as instances.

---

## A07 — Balanced two-category collision, `n = 4`, counts `(2,2)`

**Claim.** `C_hat = 1/3`, and this is **not** the naive squared-proportion
value `1/2`.

**Derivation.** With `n = 4` and two occupied categories each holding `2`:

```
C_hat = [2(2-1) + 2(2-1)] / [4(4-1)]
      = [2 + 2] / 12
      = 4 / 12
      = 1/3.
```

The naive plug-in estimate would be `(2/4)^2 + (2/4)^2 = 1/4 + 1/4 = 1/2`.

The two are related exactly. Writing `C_naive = sum_k (n_k/n)^2`, expansion of
`sum_k n_k(n_k-1) = sum_k n_k^2 - n` gives

```
C_hat = (sum_k n_k^2 - n) / [n(n-1)] = (n C_naive - 1) / (n - 1),
```

so the self-pair inflation is `C_naive - C_hat = (1 - C_naive)/(n - 1)`. Here
that is `(1 - 1/2)/3 = 1/6`, and indeed `1/2 - 1/3 = 1/6`. Check of the
identity itself: `(4 * (1/2) - 1)/3 = 1/3`. A target returning `0.5` for this
cell is using the prohibited naive estimator.

**Anchor values.** `C_hat = 1/3` (registered); `1/2` (prohibited naive value,
recorded so the harness can positively identify the wrong formula).

---

## A08 — Floor-mass ordinal capacity `K_A`

**Claim.** With `p_floor,A0 = P(Y_A0 = 1)`, the maximum attainable A-present
discrimination over every possible AB distribution is
`K_A = 1 - 0.5 p_floor,A0`, attained by placing all AB mass at category `1`.

**Derivation.** For a fixed A0 score `a`, `h(a,b)` is non-increasing in `b`, so
`h(a,b) <= h(a,1)` for every `b >= 1`. Hence `PA = sum_a sum_b p_a q_b h(a,b)`
is maximized by the degenerate `q` with `q_1 = 1`. Under that `q`:

- every A0 draw with `a > 1` is a strict win contributing `1`;
- every A0 draw with `a = 1` is a floor tie contributing `0.5`.

Therefore

```
K_A = (1 - p_floor,A0) * 1 + p_floor,A0 * 0.5
    = 1 - 0.5 p_floor,A0.
```

On the Cliff scale `K_A^delta = 2 K_A - 1 = 1 - p_floor,A0` (consistent with
A04).

**Worked instances fixed as anchors.**
`p_floor,A0 = 0    ->  K_A = 1`;
`p_floor,A0 = 0.4  ->  K_A = 1 - 0.2 = 0.8`;
`p_floor,A0 = 1    ->  K_A = 0.5`.

A target computing `K_A = 1 - p_floor,A0` (no half credit for floor ties) is
detectably wrong at any `p_floor,A0 > 0`: at `p_floor,A0 = 0.4` it returns
`0.6` instead of `0.8`.

---

## A09 — Point-mass collision equals one

**Claim.** A cell whose `n > 1` calls all fall in one category has
`C_hat = 1`.

**Derivation.** One category holds `n_k = n`, the rest hold `0`. Then
`sum_k n_k(n_k-1) = n(n-1)` and `C_hat = n(n-1)/[n(n-1)] = 1`. Every distinct
ordered pair collides, which is the definition of an empirically degenerate
cell (`m_hat = 1`).

**Anchor value.** `C_hat = 1` exactly, for every `n > 1` and every category.

---

## A10 — Section 5.3 anchor: A0 at category 2, AB at category 1

**Claim.** If all A0 mass sits at category `2` and all AB mass at category `1`,
then `p_floor,A0 = 0`, `K_A = 1`, and `PA = 1`.

**Derivation.** `p_floor,A0 = P(Y_A0 = 1) = 0` because all A0 mass is at
category `2`. By A08, `K_A = 1 - 0.5(0) = 1`. The realized `PA` has a single
occupied pair `(a,b) = (2,1)` with `a > b`, so `PA = h(2,1) = 1`.

**Significance.** This is the registered statement that "only one category of
headroom" does **not** reduce ordinal capacity. Category `2` can be ordered
above category `1` with complete probability. Any target that scales capacity
by category *distance* — for example returning `K_A = 1/9` or `0.2` because
only one of nine gaps remains — contradicts the ordinal construct and is
detectably wrong here.

**Anchor values.** `p_floor,A0 = 0`, `K_A = 1`, `PA = 1`, `delta_A = 1`.

---

## A11 — Ordinal capacity surplus `G` at exactly zero

**Claim.** `G = K_A - (P0 - M_I^P)`. With `p_floor,A0 = 0.4` (so `K_A = 0.8`)
and `P0 = 0.95`, `G = 0.8 - (0.95 - 0.15) = 0.8 - 0.8 = 0` exactly.

**Derivation.** Attenuation of at least `M_I^P` is present when
`P0 - PA >= M_I^P`, i.e. when `PA <= P0 - M_I^P`. The boundary value making
meaningful attenuation absent is `PA_nonattenuated = P0 - M_I^P`. The capacity
surplus is the signed distance between the largest attainable `PA` and that
boundary, `G = K_A - (P0 - M_I^P)`. Substituting the stated values gives `0`.

**Disposition consequence.** The registered dispositions are stated on the
*interval* for `G`, not the point estimate: `RANGE_ADEQUATE` requires the lower
simultaneous bound above zero; `FLOOR_LIMITED` requires the upper bound below
zero; otherwise `RANGE_INDETERMINATE`. A point estimate of exactly `0` can
therefore never be `RANGE_ADEQUATE`, and at finite `N` an interval containing
`0` must yield `RANGE_INDETERMINATE`. A target returning `RANGE_ADEQUATE` at
`G_hat = 0` is using a point-estimate rule where an interval rule is
registered.

**Anchor values.** `G = 0` at `(p_floor,A0, P0) = (0.4, 0.95)`;
`G = +0.15` at `(0, 1.0)`; `G = -0.30` at `(1.0, 0.95)`.

---

## A12 — Concentration capacity `K_Q` and `G_Q`

**Claim.** `K_Q = 1 - 0.5 (C_00 + C_0B)` and `G_Q = K_Q - M_C = K_Q - 0.10`.

**Derivation.** `Q = 0.5[(C_A0 - C_00) + (C_AB - C_0B)]`. Because every
collision probability is bounded above by `1`, the largest attainable value of
`Q` for fixed baselines is obtained at `C_A0 = C_AB = 1`:

```
K_Q = 0.5[(1 - C_00) + (1 - C_0B)] = 1 - 0.5 (C_00 + C_0B).
```

**Worked instances fixed as anchors.**
`C_00 = C_0B = 1` (both baselines degenerate) `-> K_Q = 0`, `G_Q = -0.10 < 0`,
so the specimen is `CONCENTRATION_RANGE_LIMITED`;
`C_00 = C_0B = 0.2  -> K_Q = 0.8`, `G_Q = +0.70`;
`C_00 = 1.0, C_0B = 0.6 -> K_Q = 0.2`, `G_Q = +0.10`.

**Significance.** This is the registered protection against a
ceiling-concentrated `00`/`0B` baseline manufacturing an C4 equivalence
conclusion merely because `Q` had no room to rise. The C4 capacity gate
withholds an C4 conclusion; per preregistration §4 and amendment §3 it must
never alter, protect, rescue, or invalidate C2.

---

## A13 — Equal specimen weighting versus call pooling

**Claim.** Equal-weight aggregation and call-level pooling give different
answers, and the registered estimand is the equal-weight one.

**Construction.** Two specimens, cell `00` versus cell `0B`:

- specimen `ordinal-profile`: `00` = 20 calls all at category 10; `0B` = 20 calls all at
  category 1. By A05, `P0(ordinal-profile) = 1`.
- specimen `S2`: `00` = 4 calls all at category 1; `0B` = 4 calls all at
  category 10. By A05, `P0(S2) = 0`.

**Registered equal-weight value.** `(1 + 0)/2 = 1/2`.

**Prohibited call-pooled value.** Pool the cells across specimens: pooled `00`
is `{10 x 20, 1 x 4}` (`n = 24`), pooled `0B` is `{1 x 20, 10 x 4}` (`n = 24`).
Cross-pairs total `24 * 24 = 576`. Enumerating the four occupied blocks:

```
X=10 (20) vs Y=1  (20) : 400 pairs, wins
X=10 (20) vs Y=10  (4) :  80 pairs, ties
X=1   (4) vs Y=1  (20) :  80 pairs, ties
X=1   (4) vs Y=10  (4) :  16 pairs, losses
```

Check: `400 + 80 + 80 + 16 = 576`. So `W = 400/576`, `T = 160/576`,
`L = 16/576`, and

```
PS_pooled = (400 + 0.5 * 160) / 576 = 480 / 576 = 5/6.
```

**Anchor values.** equal-weight `= 1/2`; call-pooled `= 5/6`. The gap `1/3` is
the detection signal for the "specimens pooled by calls instead of equally
weighted" defect class (original contract §11). The pooled value is recorded so
the harness can positively identify the wrong aggregation rather than merely
observe a mismatch.

---

## A14 — Worked non-degenerate `W/L/T` and `PS`

**Construction.** `n_X` (cell `00`, `n = 3`): two calls at category `8`, one at
category `9`. `n_Y` (cell `0B`, `n = 3`): one call each at categories `7`, `8`,
`10`.

**Derivation.** All `3 * 3 = 9` cross-pairs, blocked by category:

```
X=8 (2) vs Y=7  (1) : 2 pairs, 8 > 7  -> wins
X=8 (2) vs Y=8  (1) : 2 pairs, 8 = 8  -> ties
X=8 (2) vs Y=10 (1) : 2 pairs, 8 < 10 -> losses
X=9 (1) vs Y=7  (1) : 1 pair,  9 > 7  -> win
X=9 (1) vs Y=8  (1) : 1 pair,  9 > 8  -> win
X=9 (1) vs Y=10 (1) : 1 pair,  9 < 10 -> loss
```

Wins `= 2 + 1 + 1 = 4`; ties `= 2`; losses `= 2 + 1 = 3`. Check
`4 + 2 + 3 = 9`.

```
W = 4/9,  T = 2/9,  L = 3/9
PS = 4/9 + 0.5 (2/9) = (4 + 1)/9 = 5/9
delta = 2(5/9) - 1 = 1/9
```

**Collision of the `00` cell.** counts `(2,1)`, `n = 3`:
`C_hat = [2(1) + 1(0)] / [3(2)] = 2/6 = 1/3`.

**Anchor values.** `W = 4/9`, `L = 3/9`, `T = 2/9`, `PS = 5/9`,
`delta = 1/9`, `C_hat(00) = 1/3`.

**Detection value.** The two named tie defects are separated here:
discarding ties gives `4/7`; promoting ties to wins gives `6/9 = 2/3`. Both
differ from `5/9`.

---

## A15 — Strictly monotone relabeling invariance

**Claim.** `PS`, `W`, `L`, `T`, and every collision probability are invariant
under any strictly increasing relabeling of the ten categories; collision
probability is additionally invariant under **every** bijective relabeling,
including order-destroying ones.

**Derivation.** `h(a,b)` depends on `a` and `b` only through the sign of
`a - b`. If `phi` is strictly increasing then `sign(phi(a) - phi(b)) =
sign(a - b)`, so `h(phi(a), phi(b)) = h(a,b)` termwise and `PS` is unchanged;
the same argument fixes `W`, `L`, `T`. Collision probability `sum_k p_k^2`
depends only on the multiset of masses, which any bijection permutes, so `C` is
invariant under arbitrary relabeling.

**Anchor consequence.** Applying the strictly increasing map
`1..10 -> 1,2,3,4,5,6,7,8,9,10` restricted to any order-preserving
reassignment of occupied categories leaves A14's `PS = 5/9` unchanged; applying
the order-destroying transposition `8 <-> 10` to both cells of A14 changes `PS`
but leaves `C_hat(00) = 1/3` unchanged. Both directions are frozen: a target
whose `PS` is invariant under an order-destroying permutation has lost the
ordinal structure, and a target whose collision estimate moves under a
permutation is not computing `sum p_k^2`.

---

## A16 — Attempt-order invariance and first-valid selection

**Claim.** Two archive-level facts follow from preregistration §11.2 and are
fixed here as non-numerical anchors.

1. **First-valid retention.** "The first valid response in attempt order is
   retained as the requested replicate." Therefore, for a given
   `(light, specimen, cell, replicate_index)`, if attempt indices `0` and `1`
   are both valid, the selected score is the one at attempt index `0`,
   regardless of which score is more favorable to any hypothesis.
2. **Order invariance of the archive.** Attempt order is carried by
   `attempt_index`, not by physical row position. Permuting the rows of the
   `attempts` array while preserving every record's fields must therefore
   produce a byte-identical scientific result.

**Derivation of the detection signal.** Consider one replicate with attempt
index `0` valid and score `4`, and attempt index `1` valid and score `9`. The
registered selection is `4`. A target selecting `9` has performed favorable
replacement; because `PS` is monotone in the selected score, the induced error
in the cell's count vector is directly observable. Note that attempt index `1`
is not a permitted replacement at all here: §11.2 permits replacement only for
an enumerated technical category, and an earlier *valid* response exhausts the
need for one.

---

## A17 — Prohibited zero-width finite-sample interval

**Claim.** At finite `N`, an empirically degenerate cell (`m_hat = 1`) must
still receive a strictly positive-width confirmatory interval; a zero-width
interval is `INFERENCE_ENGINE_FAILURE`, never `SUPPORTED`.

**Derivation.** Observing `n` identical categorical draws is consistent with
every `p` whose mass on the observed category is at least some value strictly
below `1`. Concretely, for `n` i.i.d. draws all landing in category `k`, the
likelihood of the data under `p_k = t` is `t^n`, which is bounded away from `0`
for any fixed `t < 1` as long as `n` is finite. A one-sided exact bound at
level `gamma` therefore admits every `t >= gamma^(1/n) > 0`, a non-degenerate
set. Only as `n -> infinity` does the admissible set collapse to `{1}`.

**Worked instance fixed as an anchor.** For `n = 10` identical draws and a
one-sided exact level `gamma = 0.05`, the admissible lower limit is
`0.05^(1/10) = exp(ln(0.05)/10)`. Since `ln(0.05) = -2.9957322736...`, the
exponent is `-0.29957322736...` and the limit is `0.74113...` — strictly less
than `1`. The interval `[0.741..., 1]` has width `> 0.25`, not `0`.

**Anchor value.** width `> 0` is required; the specific frozen assertion is
`upper - lower >= 1e-9` for every decision-bearing interval at finite `N`.
This anchor is deliberately stated as an inequality: the exact width depends on
the confidence-region construction, which the preregistration leaves open
(see `reports/AMBIGUITY-REGISTER-v1.0.md`, ambiguity `AMB-01`).

---

## A18 — Guards can withhold but never create

**Claim.** For C1, C2, C4, and C5 alike, the recurrence, anti-singleton
(leave-one-out), and heterogeneity guards are one-directional: a guard failure
can only move a disposition *away* from `SUPPORTED` or
`EQUIVALENTLY_ABSENT`, never toward it.

**Derivation.** The registered rules have the form

```
SUPPORTED            <=> interval_condition AND positive_guards
EQUIVALENTLY_ABSENT  <=> equivalence_interval_condition AND heterogeneity_guards
```

Both are conjunctions in which the guard is a necessary, not sufficient,
conjunct. Formally, for any scenario `s`, let `D(s)` be the disposition with
guards enforced and `D'(s)` the disposition with the guard clause deleted.
Then `D(s) = SUPPORTED` implies `D'(s) = SUPPORTED`, and the converse fails
exactly on the guard-failure set, where `D(s) = INDETERMINATE_GUARD_NOT_MET`.
There is no scenario in which enforcing a guard produces `SUPPORTED` where
deleting it would not.

**Anchor consequence (frozen as a harness check, not a number).** For every
scenario in the clean panel and every registered mutant, the set of
`SUPPORTED` verdicts under guards enforced must be a **subset** of the set
under guards deleted, and likewise for `EQUIVALENTLY_ABSENT`. A target for
which a guard failure yields `SUPPORTED` violates the monotonicity above.

---

## A19 — Attenuation chain and C4 non-interference

**Claim.** `A_l = C1_l AND RANGE_l AND VALIDITY_l AND C2_l` is a conjunction of
four necessary conditions, and C4 is not a conjunct of any C2 or `A_l`
condition.

**Derivation.** Preregistration §4 (C3-light) defines `A_l` as exactly that
four-way conjunction "including every prospectively frozen recurrence,
heterogeneity, degeneracy, refusal, provenance, cache, and inference-engine
requirement attached to those components". §4 (C4) states that the C4
diagnostic "does not alter the definition or truth of C2", and §12.3 opens the
C4 family only "for a light with supported `A_l`". Therefore the dependency
runs strictly `A_l -> C4`, never `C4 -> C2`.

**Anchor consequences (frozen as harness checks).**
1. If `VALIDITY_l` fails, `A_l` must not be supported for any numeric values.
2. If `RANGE_l` is not cleared, C2 must receive `RANGE_NOT_CLEARED` and neither
   support nor equivalence, for any numeric values.
3. If C1 is not supported, no C2 support or equivalence may be declared.
4. Changing only the C4 inputs (the `A0`/`AB`/`00`/`0B` concentration pattern)
   in a way that leaves all four `W/L/T` cross-tabulations — and hence `P0`,
   `PA`, `I_P`, `p_floor,A0`, `G` — unchanged must leave C1, range, and C2
   bit-identical. This is the operative test that C4 cannot protect, overwrite,
   rescue, or invalidate C2.
5. C4 must be reported ineligible, not absent, for a light whose `A_l` is not
   supported.

**Realizability note for consequence 4.** Such a pair exists: permuting which
*specific* calls within a cell occupy categories does not change the cell's
count vector, so instead the frozen fixture pair changes `A0`/`AB` counts in a
way that holds each cross-tabulation fixed — see scenario
`CL-C4-NONINTERFERENCE-A/B`, whose construction is verified by the executable
oracle to leave `P0`, `PA`, `I_P`, and `G` exactly equal while moving `Q`.

---

## A20 — `A_all` is a conjunction, not a vote

**Claim.** `A_all = A_L1 AND A_L2 AND A_L3`. A mixed light vector earns no
`A_all` and is never replaced by a pooled verdict.

**Derivation.** Preregistration §4 (C3-light) and §12.3 state the conjunction
explicitly and add that "one or two supported lights remain confirmatory
configuration-specific findings but do not earn cross-light generalization",
and §13 routes a mixed vector to per-light reporting with "no common pooled
effect".

**Anchor consequence.** For the frozen mixed-vector scenarios, `A_all` must be
false whenever any `A_l` is false, and the three per-light dispositions must
each still be reported. A target emitting `A_all` on two of three lights, or
emitting an unregistered pooled disposition in place of the vector, is
detectably wrong.

---

## Summary table of exact numerical anchors

| ID | Quantity | Exact value | Decimal |
|---|---|---|---|
| A01 | `PS` (identical point masses) | `1/2` | `0.5` |
| A01 | `W`, `L`, `T` | `0`, `0`, `1` | — |
| A02 | `PS(X,Y) + PS(Y,X)` | `1` | `1.0` |
| A04 | `delta` at `PS = 7/10` | `2/5` | `0.4` |
| A04 | `I_delta` at `I_P = 3/20` | `3/10` | `0.3` |
| A05 | `PS` complete separation | `1` | `1.0` |
| A05 | `PS` reverse separation | `0` | `0.0` |
| A07 | `C_hat`, counts `(2,2)`, `n=4` | `1/3` | `0.333333...` |
| A07 | prohibited naive value | `1/2` | `0.5` |
| A08 | `K_A` at `p_floor = 2/5` | `4/5` | `0.8` |
| A08 | `K_A` at `p_floor = 1` | `1/2` | `0.5` |
| A09 | `C_hat` point mass | `1` | `1.0` |
| A10 | `K_A`, `PA` (5.3 case) | `1`, `1` | `1.0`, `1.0` |
| A11 | `G` at `(0.4, 0.95)` | `0` | `0.0` |
| A12 | `K_Q` at `C_00 = C_0B = 1` | `0` | `0.0` |
| A12 | `G_Q` at `C_00 = C_0B = 1` | `-1/10` | `-0.1` |
| A13 | equal-weight aggregate | `1/2` | `0.5` |
| A13 | prohibited call-pooled value | `5/6` | `0.833333...` |
| A14 | `PS` worked case | `5/9` | `0.555555...` |
| A14 | ties-discarded value | `4/7` | `0.571428...` |
| A14 | ties-as-wins value | `2/3` | `0.666666...` |
| A14 | `C_hat` counts `(2,1)`, `n=3` | `1/3` | `0.333333...` |

Non-numerical anchors A03, A15, A16, A17, A18, A19, A20 are frozen as
structural assertions and are checked as predicates rather than values.

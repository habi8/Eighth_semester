# Cross-fade blending in CLALHE.py — what it is, and why not bilinear interpolation

## 1. What the cross-fade actually does

Three steps, in `CLALHE.py` lines 224-254 (`part2_enhance`):

1. **Read wider than you write.** Subimage `(r, c)` owns the core rectangle
   `[y_start:y_end, x_start:x_end]`, but CLAHE is applied to an *extended* window
   padded by `margin_y` / `margin_x` on every **shared** side. So each subimage's
   transform is actually evaluated on territory that belongs to its neighbours.

2. **Build a partition of unity.** `_blend_profile` (line 151) returns a 1-D weight
   that is 1.0 in the core interior and ramps linearly down to 0 across a
   `2*margin` wide band centred exactly on each shared boundary. Two neighbours'
   ramps are mirror images over the same band, so their weights sum to 1.0
   pointwise. The 2-D weight is the separable outer product
   `w_y[:, None] * w_x[None, :]`.

3. **Accumulate and normalise.** `accumulator / weight_total` — a weighted average
   of every subimage transform that covers that pixel.

`ramp_head` / `ramp_tail` are gated on `r > 0` / `r < rows - 1` (and likewise for
columns), so image borders keep weight 1 and do not fade out.

## 2. Why this isn't "instead of" bilinear interpolation — it *is* bilinear interpolation

This is the key point. Every contributing subimage transform is applied to the
**same input pixel value** `v`, so a weighted average of the *outputs* equals the
same weighted average of the *transfer functions*:

```
out(y, x) = Σ wᵢ(y, x) · Tᵢ(v)  =  [ Σ wᵢ(y, x) · Tᵢ ](v)
```

And the weights `wᵢ` are products of two linear ramps, which in the four-way
overlap at a corner is exactly the bilinear weighting

```
(1-a)(1-b),   a(1-b),   (1-a)b,   ab
```

So the code performs bilinear interpolation of the subimage mappings. It simply
evaluates it in **image space** rather than **LUT space**, which is the only
representation available here.

## 3. Why not do it Zuiderveld-style, in LUT space?

Zuiderveld's CLAHE can interpolate cheaply because it *owns* the LUTs: for a given
pixel it looks up `v` in the four surrounding tiles' CDF tables and blends four
scalars. Two things block that approach in this implementation:

- **`cv2.createCLAHE().apply()` is a black box.** It returns pixels, not the
  per-tile CDFs (see `_apply_clahe_with_params`, lines 108-111). To obtain LUTs you
  would have to reimplement clipped histogram equalisation from scratch — clipping,
  excess redistribution, CDF construction, per-tile mapping — replacing a
  well-tested implementation with your own.

- **A subimage has no single LUT to interpolate.** Each subimage is *itself*
  internally tiled `cbd × cbd` and internally bilinearly interpolated by OpenCV. Its
  mapping is therefore already spatially varying: "the transfer function of
  subimage A" is not one table, it is a field of tables. Evaluating subimage A's
  mapping at a pixel *inside* subimage B would mean extrapolating A's tile LUTs
  beyond A's own extent, over data those histograms never saw. The overlap margin
  solves precisely this: it computes A's mapping there from **real pixels** instead
  of extrapolating.

**Is LUT-space interpolation feasible here?** Only if you rewrite CLAHE and then
design a two-level (subimage → tile) interpolation scheme. That is a large amount
of new, untested surface area for a result that converges to what the cross-fade
already produces.

## 4. Advantages of the image-space cross-fade

- **Correctness by construction.** Weights sum to 1 across every boundary, so there
  is no brightness drift and no residual step; the `weight_total` normalisation
  keeps it robust even where that assumption is violated.
- **Uniform handling of edges, corners, and any `rows × cols` grid** — none of the
  border special-casing that LUT-space CLAHE interpolation requires.
- **Separable and cheap.** Two 1-D weight vectors per subimage; `O(h + w)` weight
  computation, one fused multiply-add over the window.
- **Part 1 is untouched.** The ONS / SID / CBD / I_CL logic from the paper is
  unchanged; only the write-back differs.
- **Works with the stock, well-tested OpenCV CLAHE path** — no reimplementation risk.

## 5. Costs and caveats (state these in the write-up)

- **Redundant compute.** Margin bands are processed twice, and four times at
  corners. With `blend_ratio = 0.25` on a 2×2 grid each window grows ~1.25× per
  axis ≈ 1.56× in area. Minor.
- **Mild contrast dilution inside the blend band.** Averaging two mappings is
  inherently smoothing. This is the same trade-off CLAHE's own internal
  interpolation makes. `blend_ratio` is the knob: larger = smoother seams but weaker
  local adaptation; smaller = sharper adaptation but risk of residual banding.
- **Accuracy caveat in the current docstring.** Lines 31-33 claim the independent
  histograms are "untouched", but they are not quite: CLAHE runs on the *extended*
  window, so the internal tile grid and the histograms feeding it include margin
  pixels. The subimage count and core dimensions are preserved; the histograms are
  slightly widened. A more accurate phrasing: *the subdivision is preserved and each
  subimage still derives its mapping from its own local statistics plus a thin
  margin of context.*

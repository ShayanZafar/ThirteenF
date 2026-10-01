# Conviction meter

How much of a manager's reported 13F portfolio one position takes up, with last quarter's weight as a tick.

**Use** wherever a holder appears: the full meter on a company's holder panel, the mini meter (`tf-meter--mini`) inside the Holder table. A big weight in a concentrated book says more than a large dollar value in a huge index fund; this is how that shows.

**Provide**: manager name, weight this quarter and last (position value ÷ the manager's total reported 13F value), rank among their positions, and position count. Set `--pct` on the fill and the prior tick as the weight on a 0–10% scale (10% or more pins to the end and the label reads the true value).

**Markup**

```html
<div class="tf-meter" role="meter" aria-valuemin="0" aria-valuemax="10" aria-valuenow="8.9"
     aria-label="Stillwell Partners: 8.9% of reported portfolio, was 6.1%">
  <div class="tf-meter__head"><span>Stillwell Partners</span><span class="tf-meter__value">8.9%</span></div>
  <div class="tf-meter__track">
    <span class="tf-meter__fill" style="--pct: 89%"></span>
    <span class="tf-meter__prior" style="--pct: 61%"></span>
    <span class="tf-meter__mark" style="--pct: 50%"></span>
  </div>
  <div class="tf-meter__foot"><span>#2 of 31 positions</span><span>was 6.1% in Q1</span></div>
</div>
```

- The fill is `ink`: weight is a filed fact, not a direction. The track is `paper-shade`; the prior tick is `ink-muted` with a `paper` ring so it reads over the fill.
- `tf-meter__mark` at 50% marks the 5% line; keep the scale identical on every meter in a view.
- Omit the prior tick for new positions and say "new this quarter".
- The weight is a share of long 13F positions only (no shorts, cash or non-US listings). Say that once per page in a `type-note`.

**Don't** color the fill by change, or compare weights across different quarters' scales.

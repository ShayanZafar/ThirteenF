# Key figure

The few numbers a page leads with, in one row under the page title.

**Use** for the headline facts about one company, manager or screen: ownership, holder count, net flow, the valuation gap. One row per view, three to five figures. If there is only one number that matters, show one.

**Provide** for each figure: a label that names the period ("Net 13F flow, Q2"), the value already formatted, and optionally a delta against a named period.

**Markup**

```html
<div class="tf-kfrow">
  <div class="tf-kf">
    <span class="tf-kf__label">Institutional ownership</span>
    <span class="tf-kf__value">71.4<span class="tf-kf__unit">%</span></span>
    <span class="tf-kf__delta tf-kf__delta--in"><span class="tf-dir tf-dir--in"></span><b>+3.2 pts</b> vs Q1</span>
  </div>
  <div class="tf-kf tf-kf--est">…</div>
</div>
```

- Values are `ink` in the sans at 32px with proportional figures (`type-figure`). Never set them in the serif.
- A delta that is a flow takes `tf-kf__delta--in` or `--out`, a triangle and a signed number. Only the number is colored; the period stays `ink-muted`.
- A model-derived figure takes `tf-kf--est`: the value turns `estimate` and its unit says "est.".
- Figures sit on `paper`, divided by `rule` hairlines, not boxed in cards.

**Don't** add sparklines to every figure, round away the sign, or show a delta without naming what it is compared with.

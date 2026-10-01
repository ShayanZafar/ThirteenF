# Flow bar

A ranked list of names with a bar that grows right for net buying and left for net selling, around one zero line.

**Use** to show where institutional money moved in a period: across a watchlist, a sector, or one manager's changes. Sort by the signed value, largest inflow first. Up to about 15 rows; beyond that, show the top and bottom and link to the full table.

**Provide** per row: ticker, name, the signed net flow already formatted, and `--w`, the absolute value as a percentage of the largest absolute value in the list. Choose the bar class by sign.

**Markup**

```html
<figure class="tf-flow">
  <figcaption class="tf-flow__head"><span class="type-title">Net 13F flow, Q2 2026</span></figcaption>
  <div class="tf-flow__axis" aria-hidden="true">…</div>
  <ol class="tf-flow__rows">
    <li class="tf-flow__row">
      <span class="tf-flow__name"><span class="tf-ticker">CLFR</span><span>Calder Freight</span></span>
      <span class="tf-flow__track"><span class="tf-flow__bar tf-flow__bar--in" style="--w: 93.8%"></span></span>
      <span class="tf-flow__value">+$377M</span>
    </li>
  </ol>
</figure>
```

- Bars are `flow-in` and `flow-out`, `size-bar` thick, rounded only at the data end, growing from the `rule-strong` zero line.
- Values stay `ink`, tabular, with a real sign (+ or −, U+2212). The color is in the bar, not the text.
- Add `tf-hl` to a row only when that name is also below its est. value range (it is worth a look). At most five per view.
- Net flow is shares changed × quarter-end price across all 13F filers for that period. Say so in a `type-note` under the chart.
- Every bar needs a tooltip or the value column, and the chart needs a table view.

**Don't** mix periods in one list, color the value text, or use these colors for price moves.

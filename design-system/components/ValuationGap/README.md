# Valuation gap

Where the price sits against an estimated value range: a badge that says it in words, and a strip that shows it.

**Use** next to any company that appears with a flow signal, and on the company page under the key figures. The badge alone fits in tables and lists; the strip needs about 240px.

**Provide**: last price and its date, the estimated range (low, high) and its midpoint, and the method behind it. Compute the gap as price ÷ midpoint − 1, rounded to a whole percent. Inside the range, say "Within est. range" instead of a percentage. For the strip, set `--lo`, `--hi`, `--mid` and `--price` as positions (0–100%) on a scale that runs a little past the lowest and highest of price and range.

**Markup**

```html
<span class="tf-gap">31% below est. value</span>

<div class="tf-gapstrip" style="--lo: 44.6%; --hi: 85.2%; --mid: 64.9%; --price: 13.6%"
     role="img" aria-label="Price 50.30 dollars; estimated value 64 to 82 dollars, midpoint 73">
  <div class="tf-gapstrip__track">
    <span class="tf-gapstrip__range"></span><span class="tf-gapstrip__mid"></span><span class="tf-gapstrip__price"></span>
  </div>
  <span class="tf-gapstrip__label tf-gapstrip__label--est">Est. $64–$82</span>
  <span class="tf-gapstrip__label tf-gapstrip__label--price">$50.30</span>
</div>
```

- The price is a fact: an `ink` dot with a `paper` ring. The range is an estimate: an `estimate-soft` band with `estimate` edges and midpoint tick. That split is the point of the component; keep it.
- The badge is always `estimate` on `estimate-soft`, whether the gap is below, within or above. Direction is in the words, and the words always say "est.".
- A wide range means low confidence. Show it as it is; never shrink it to a single fair-value number.
- Put the method in a `type-note` near the first gap on a page.

**Don't** use `flow-in`/`flow-out` for cheap or expensive, write "undervalued" as a verdict, or show a gap without its range.

# Holder table

The evidence behind a flow: which managers opened, added, trimmed, held or exited a position in one quarter's 13F filings.

**Use** on a company page under the flow chart, and on a manager page (one row per position). Default sort: position value, exits last.

**Provide** per row: manager name, change type, signed share change, position value at quarter end, weight in the manager's reported 13F portfolio this quarter and last. The footer states how many holders exist, the filing type and the as-of date.

**Markup**

```html
<div class="tf-tablewrap">
  <table class="tf-table">
    <caption><span class="type-title">Largest holders of CLFR, Q2 2026</span></caption>
    <thead><tr><th scope="col">Manager</th><th scope="col">Change</th><th scope="col" class="tf-r">Shares</th>…</tr></thead>
    <tbody>
      <tr>
        <td>Stillwell Partners</td>
        <td><span class="tf-tag tf-tag--add">Add</span></td>
        <td class="tf-r">+860K</td>
        …
      </tr>
    </tbody>
    <tfoot><tr><td colspan="5">6 of 214 holders · 13F-HR filings for Q2 2026 · positions as of Jun 30, 2026</td></tr></tfoot>
  </table>
</div>
```

- Change tags, strongest to weakest: `tf-tag--new` (solid `flow-in`), `--add` (tinted), `--hold` (outlined), `--trim` (tinted `flow-out`), `--exit` (solid). The word is always visible; color never works alone.
- Numbers use `tf-r`: right-aligned, tabular, `ink`. Signs are + and − (U+2212). An exited position's value is an em dash in `ink-muted`, not $0.
- Header band is `paper-shade` with `type-caption` labels; rows are `size-row` tall with `rule` dividers and a `paper-shade` hover.
- The weight column holds a mini Conviction meter (`tf-meter--mini`) with the prior-quarter tick.
- Wrap in `tf-tablewrap` so narrow screens scroll the table, not the page.

**Don't** zebra-stripe, bold whole rows, or mix quarters in one table. Apply amendments (13F-HR/A, which either restate a filing or add holdings to it) before display, and note them in the footer.

ThirteenF shows where institutional money is concentrating, from 13F filings and other public records, and sets it beside an estimate of what each company is worth. It serves long-term decisions, so it reads like an analyst's desk rather than a trading screen: paper and ink, dated facts, a blue pen for estimates, and a highlighter used sparingly.

## Principles

- **Filed facts in ink, estimates in pen.** Anything taken from a filing or the market (shares, position values, holder counts, prices, dates) is `ink`. Anything a model produced (fair-value ranges, valuation gaps, scores) is `estimate` and says "est.". Never blend the two in one number.
- **Every number has a date.** 13F positions describe the last day of a quarter and arrive up to 45 days later. Put a Freshness stamp beside every source on a page and never imply live data.
- **Color is evidence.** Only three things get color: flow direction (`flow-in`, `flow-out`), estimates (`estimate`) and the `highlight`. Everything else is `ink` on `paper`.
- **Evidence before verdicts.** A highlighted name always shows, on the same screen, who bought, how much of their book it is, and the estimate's full range.

## Content

Write like a careful analyst's note: plain, precise, unhurried. Sentence case everywhere; uppercase only through `type-caption` and tickers. Address the reader as "you" only in help and empty states. No exclamation marks, no emoji.

- Name the period in any title or label that carries a number: "Net 13F flow, Q2 2026".
- Describe what filers did; don't recommend. "31 of 42 tracked managers added shares", not "smart money is piling in".
- A highlighted name is "Worth a look". The app never says buy, sell, or undervalued.

| Say | Don't say |
| --- | --- |
| Added, opened a new position, accumulating | Loading up, buying spree |
| Trimmed, exited, distributing | Dumping, fleeing |
| 31% below est. value | Undervalued, cheap, a bargain |
| Worth a look | Buy, top pick, opportunity |
| Managers, holders, filers | Smart money, whales |
| As of Jun 30, 2026 | Live, real-time, latest |

### Numbers

| Kind | Format | Example |
| --- | --- | --- |
| Money | $ and 3 significant digits, K / M / B | $377M · $1.84B · $93.2M |
| Signed change | + or − (U+2212, never a hyphen) | +$377M · −540K |
| Shares | compact, "sh" where the column doesn't say | 2.41M sh |
| Portfolio weight | one decimal | 8.9% |
| Change in a percentage | points | +3.2 pts |
| Valuation gap | whole percent in words | 31% below est. value |
| Dates and periods | Mon D, YYYY · Q2 2026 | Jun 30, 2026 |
| Age | whole days | 92d |
| Tickers | `tf-ticker` | CLFR |
| Identifiers | `type-id` | 0001234567-26-000118 |

An exited position's value is an em dash, not $0. Round only for display; tooltips and table views may show full precision.

## Visual foundations

### Color

- Page ground is `paper`. Floating layers (tooltips, popovers, menus) are `paper-raised` with `shadow-pop`. Table header bands, row hover, meter and strip tracks are `paper-shade`.
- Text is `ink` for primary copy and every filed number, `ink-muted` for labels, captions, axis ticks and as-of lines. Both hold 4.5:1 on every paper token and on `highlight`, in both themes.
- `flow-in` (bluish green) means money in; `flow-out` (vermilion) means money out. They differ in hue and lightness and always travel with a sign and a triangle, so they survive color blindness and grayscale. Use them for bars, triangles, change tags and signed deltas, and for nothing else: not price moves, not gains, not errors, not valuation.
- `flow-in-soft` and `flow-out-soft` sit behind their own color's text (Add, Trim tags). Text on a solid flow fill is `on-flow` (New, Exit tags).
- `estimate` is the blue pen for model output, in text and marks; `estimate-soft` is its band and badge ground.
- `highlight` is the highlighter: a wash behind the few rows, points or phrases where net buying and a gap below est. value agree. At most five per view, always with the `tf-flag` "Worth a look" marker. Text directly on it is `ink` or `ink-muted`.
- `rule` draws hairlines (row dividers, gridlines). `rule-strong` draws anything that must be seen: control borders, zero lines, axes, stamp outlines, de-emphasized chart dots.
- Focus is `focus-ring` on every interactive element: a 2px paper gap, then a solid 2px ink ring.

### Type

- Newsreader (`--font-serif`) names things: page titles `type-display`, section heads `type-headline`, table and chart titles `type-title`, method notes and caveats in italic `type-note`.
- Public Sans (`--font-sans`) carries data and interface: `type-body`, `type-label`, `type-data`, `type-caption`, `type-figure`.
- Never set numbers in the serif. Key figures use `type-figure` with proportional figures; table cells and axis ticks use `type-data` with tabular figures (`tf-num`, or `tf-r` in tables), right-aligned.
- `type-caption` is always uppercase: table headers, eyebrows, stamps.
- `type-id` in the system mono is for strings people copy: CIK, CUSIP, accession numbers.

### Space and layout

- 4px base. `space-2` inside tags and controls, `space-3` for table cell sides, `space-4` between components, `space-8` between page sections, `space-12` above the page title.
- Page anatomy, top to bottom: title with Freshness stamps → one row of Key figures → the signal (Opportunity map or Flow bars) → the evidence (Holder table, Conviction meters, Valuation gap) → method notes in `type-note`.
- Content is at most `size-content` wide. Table rows are `size-row` tall.
- Separate with hairlines and space, not boxes. A card (`paper-raised`) is only for something that floats.

### Shape and depth

- Near-square: `radius-xs` for tags, stamps and the flag; `radius-sm` for bar data ends, buttons, inputs and tooltips; `radius-full` only for dots.
- Borders, not shadows. `shadow-pop` is for floating layers only.

### Charts

- Diverging charts grow from one `rule-strong` zero line: `flow-in` right or up, `flow-out` left or down. Bars are `size-bar` thick, rounded at the data end, square at the zero line.
- One y-axis per chart, never two. Gridlines are solid `rule` hairlines.
- Values, labels and legends stay `ink` or `ink-muted`; color lives in the marks.
- Every chart has a tooltip (value first, label second, inserted as text) and a table view with the same numbers.
- Label selectively: the highlighted points, the extremes, never every mark.

### Motion

Quiet. 120ms color and opacity transitions on hover and focus only; nothing counts up, slides in or pulses. Honor `prefers-reduced-motion`.

## Data freshness

Each source arrives at its own speed; the Freshness stamp shows it.

| Source | What it shows | Arrives |
| --- | --- | --- |
| 13F-HR | Long positions in US-listed stocks, ETFs and options, from managers with $100M+ in 13(f) securities. No shorts, no cash. | Up to 45 days after quarter end; positions are dated to quarter end |
| Form 4 | Insider buys and sells | Within 2 business days of the trade |
| Schedule 13D / 13G | Stakes above 5% (13D signals intent to influence) | 13D within 5 business days; 13G within 5 business days or 45 days after quarter end, depending on the filer |
| Short interest (FINRA) | Shares sold short | Twice a month, about a week after settlement |
| 10-Q / 10-K (XBRL) | Fundamentals that feed estimates | 40 to 90 days after period end |
| Price | Market close | End of day |

## Iconography

- No icon set yet. Direction is the CSS triangle `tf-dir--in` / `tf-dir--out`, always beside a signed number. "Worth a look" is the `tf-flag` diamond. Everything else is words.
- No emoji, illustrations or photos.
- There is no logo yet: set "ThirteenF" in Newsreader at `type-display` or larger.

## Patterns

All classes are in `components/bundle.css`, prefixed `tf-`; no JavaScript is required except the Opportunity map tooltip.

- **Key figure**: the three to five numbers a page leads with.
- **Flow bar**: net institutional flow per name, diverging around zero.
- **Holder table**: who opened, added, held, trimmed or exited.
- **Conviction meter**: a position's weight in each manager's reported portfolio.
- **Valuation gap**: price against the est. value range, as a badge and a strip.
- **Opportunity map**: valuation gap against net buying; the highlighted corner is where both agree.
- **Freshness stamp**: source, as-of date and age.

## Using this system

- Load `tokens.css`, then `components/bundle.css`. Set `data-theme="light"` (Paper) or `data-theme="dark"` (Night desk) on `<html>`; Paper is the default.
- Use tokens through CSS variables (`var(--ink)`, `var(--space-4)`); never paste hex values. Type styles are classes: `type-display` through `type-id`.
- Copy markup from each pattern's preview; its README lists what data it needs.
- Sample data in the previews is fictional. Real screens use real filings and label every estimate.

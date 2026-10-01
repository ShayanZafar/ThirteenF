# Freshness stamp

A small label that says where a number came from and how old it is.

**Use** once per source per view, beside the page title or a panel title: every page that shows 13F data shows a 13F stamp. 13F positions describe the last day of a quarter and arrive up to 45 days later; the stamp keeps their age in sight.

**Provide**: the source name, the as-of date (the date the data describes, not the date you fetched it) and the age in days. For a filing window in progress, the count filed so far and the deadline.

**States**

| State | Class | When |
| --- | --- | --- |
| Current | `tf-stamp` | The latest period whose deadline has passed |
| Arriving | `tf-stamp--arriving` | Between quarter end and the 13F deadline, while new filings come in |
| Stale | `tf-stamp--stale` | A manager has not filed the latest period, or data is older than one full filing cycle |
| Estimate | `tf-stamp--est` | The source is a model run, not a filing; the source name turns `estimate` |

**Markup**

```html
<span class="tf-stamp"><b>13F</b><i>·</i>As of Jun 30, 2026<i>·</i>92d</span>
<span class="tf-stamp tf-stamp--stale"><b>Stale</b><i>·</i>Last filed for Q1 2026</span>
```

- Text is `type-caption` scale in `ink-muted` with the source in `ink`; the outline is `rule-strong`. Stale is a dashed outline and the word "Stale" first. No color is spent on staleness.
- Dates follow the number format: Jun 30, 2026; ages in whole days with "d".
- Link the stamp to the underlying filing on EDGAR when there is one.

**Don't** write "live" or "real-time" for any filing-based number, or hide a stale stamp.

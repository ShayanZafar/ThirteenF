# ThirteenF designs

Exported Sep 30, 2026 from the ThirteenF design system and the ThirteenF App Preview canvas. The canvas is the working copy; re-export when it changes.

## Principles

1. One question for every stock: are more funds holding it, or fewer? Ask it of the whole market to see where money is moving, or of one stock to see its history. Shopify is only the example used in the designs.
2. Two numbers per period: how many funds hold it, and how many shares they hold. They can disagree: Shopify, for example, has more funds than two years ago but fewer shares.
3. Compare with the tide. Most stocks gain holders every Dec 31 as new managers start filing, so compare with all 13F filers or the market median, never with zero. The designs say "watchlist median" because they were drawn from eight stocks; the app uses the market median.
4. Check before showing. A share total that grows far faster than its value is a filing error until proven otherwise.
5. Every number has a date and a source.

## Folders

- `../design-system/`: the design system, kept where it was first saved. Tokens, the `tf-` pattern classes, fonts, and the style guide in its `README.md`. Each pattern in `design-system/components/` has a README (what data it needs) and a `preview.html` with its markup.
- `screens/`: each screen as a static page linked to `../design-system/`. Open one in a browser; add `#dark` to the URL for the dark theme. `screens/png/` has full-page screenshots in both themes.

## Screens

| Screen | File | Data in the design | Build |
| --- | --- | --- | --- |
| Look up a stock | `screens/lookup.html` | Real, with Shopify as the example; the page works for any stock | Phase 3 |
| Biggest changes, all stocks | `screens/most-bought-and-sold.html` | Sample: fictional companies | Phase 4: the two ranked tables at the bottom, simplified (see the build plan); the top half holds an older overview layout |
| Overview (watchlist) | `screens/overview.html` | Real: 8 example stocks, from 13f.info; any stock can be added | Phase 5 |
| Company | `screens/company.html` | Sample: fictional company | Phase 7: holder table and conviction meters |
| Manager | `screens/manager.html` | Sample: fictional manager | Later |

The real numbers in the designs come from 13f.info. The app computes its own from the SEC's data sets (see `../docs/13f-data.md`), so small differences are expected.

## Using the designs in code

- Link `design-system/tokens.css`, then `design-system/components/bundle.css`. Set `data-theme="light"` or `"dark"` on `<html>`.
- Reuse the screens' markup and classes; replace the numbers with template values. The exported pages keep the canvas's inline styles for layout, which are fine to move into a small app stylesheet built on the same variables.
- Charts are inline SVG. Generate them on the server from the same classes (`tf-map__grid`, `tf-map__tick`, `tf-map__label`, `tf-map__in`, `tf-map__out`).

## Links

- Design system: https://claude.ai/code/artifact/877afe76-7a78-4c81-8e8f-a6bed961242b
- App preview canvas: https://claude.ai/artifact/JGeJo2yz5x9ToGPMfR3mtY

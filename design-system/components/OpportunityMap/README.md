# Opportunity map

A scatter of companies by valuation gap (x) and net 13F buying (y), with the corner where both agree washed in the highlighter.

**Use** as the lead chart of a screen or watchlist: it answers "where is institutional money concentrating in names that trade below est. value?" in one look. One map per view, 10 to 60 points.

**Provide** per company: ticker, name, gap to est. value in percent (price ÷ midpoint − 1), and net 13F buying as a percent of shares outstanding for the period. Also the two thresholds that define the corner (defaults: at least 15% below est. value, at least 1% net buying) and the period.

**Structure**

- One SVG with a `viewBox` inside `<figure class="tf-map"><div class="tf-map__scroll">…</div></figure>`: it scales down to 560px, then scrolls sideways inside its own box so labels stay readable on phones. Plot x from −50% to +50% and y from −4% to +4%; clamp outliers to the edge and say so in the tooltip.
- The corner is a `tf-map__quad` rect (`highlight`). Points inside it are `tf-map__pt--hl` (`ink`) and carry a ticker label; all others are `tf-map__pt` (`rule-strong`), unlabeled.
- Zero lines are `tf-map__zero`; gridlines `tf-map__grid`; tick labels `tf-map__tick`; axis titles `tf-map__axis`. The y title starts with a `flow-in` triangle because up means money in.
- Each point gets a transparent `tf-map__hit` circle (r = 12, `tabindex="0"`, an `aria-label` with both values). Hover and focus show `tf-map__tip`, a sibling of the scroll box, positioned from the point's and the figure's bounding boxes: values first, labels after. Insert labels with `textContent`.
- Under the chart: the `tf-flag` with the thresholds in words, and a "Table view" with the same data.

**Keep in mind**

- The x axis is an estimate and the y axis is a filing that is weeks old. Show both freshness stamps on the page.
- A point in the corner is a reason to read the evidence (Holder table, Valuation gap), not a conclusion. The copy says "Worth a look", never "Buy" or "Undervalued".
- Never add a second y-scale, color points by sector, or label every point.

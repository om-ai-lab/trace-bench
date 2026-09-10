# Interactive results explorer

English | [简体中文](results-explorer.zh-CN.md)

Open [the English explorer](results/index.html) or
[the Chinese explorer](results/index.zh-CN.html) in a browser after downloading
the repository. Both pages are self-contained: no build, backend, model service
or network connection is required to explore results. GitHub's repository view
shows HTML source rather than running it; download/open locally or enable Pages.

The README keeps a static cross-task scorecard and representative figures.
The explorer adds model/group filtering, visible-column sorting, clickable
headers, task-specific quality-versus-operation plots and configuration details.
Hiding the active sort column selects another visible metric. All hidden columns
leave an unsorted model list. QA plots use accuracy on the vertical axis;
Proactive uses SWA or TCR. Horizontal choices include completion, recorded tokens,
query-stage duration (QA), and extra responses (Proactive). Missing observations
are omitted from plots and retained as N/A in tables.

## Result interpretation

This is the same report cohort as [the results page](benchmark-results.md), not
a new inference or scoring run. Model-level and system-level boundaries remain
separate. On the cross-task scorecard, groups follow Proactive boundaries; AURA's
QA input is non-native. Bold values mark within-group best observations, including
ties, not statistical significance. The report QA parser differs from Core's
strict default. Output tokens are observed totals, not equal compute costs.

The two HTML pages embed identical numerical data and behavior. When updating
results, update both pages, the README tables and the result documentation together;
preserve population, missing-value and provenance notes.

## Optional GitHub Pages publication

After committing and pushing the files yourself, open the repository's
**Settings → Pages**, select **Deploy from a branch**, and choose the branch
containing this revision with the **/docs** folder. The explorer entry path is
`/Open-Stream-Bench/results/`; the Chinese page is `results/index.zh-CN.html`
relative to the project site root. This revision adds the local files only;
it does not enable Pages, change branches or push anything.

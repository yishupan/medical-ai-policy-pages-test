# Public data boundary

The GitHub Pages site publishes policy facts only.

Allowed fields:

- title
- issuer
- document number
- publication date
- region
- topic category
- official source URL

Not published:

- policy judgments, summaries, recommendations, owners, or internal hypotheses
- validity conclusions, citation priority, parsing notes, or review status
- local paths, source archives, Markdown bodies, embedded documents, or attachments
- expert consensus and policy observation records

The scheduled monitor writes newly discovered links to `data/candidates.json`. A candidate is not displayed on the public site until its official source and factual metadata have been reviewed and it has been added to `data/policies.json`.

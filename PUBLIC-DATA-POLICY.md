# Public data boundary

The GitHub Pages site publishes policy facts only, plus desensitized public excerpts from the speed-handbook.

Allowed fields:

- policy index ID
- title
- issuer
- document number
- publication date
- region
- topic category
- official source URL
- important original excerpts copied from official text
- official interpretation summary when a stable public interpretation exists, or a neutral "none / cite the original" note when it does not
- official interpretation URL when a stable public interpretation link exists

Not published:

- policy judgments, summaries, recommendations, owners, or internal hypotheses
- validity conclusions, citation priority, parsing notes, or review status
- local paths, source archives, Markdown bodies, embedded documents, or attachments
- expert consensus and policy observation records
- internal analysis sections such as `内部研判` or non-public applicability advice

The scheduled monitor writes newly discovered links to `data/candidates.json`. A candidate is not displayed on the public site until its official source and factual metadata have been reviewed and it has been added to `data/policies.json`.

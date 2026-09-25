# Plan and open questions

## v0 (this PR): public data only
- [x] NCUA 5300 ingest for all US CUs, current quarter plus year-ago quarter (YoY growth)
- [x] Ratios: loan/share, net worth, ROA, liquidity, long-asset concentration, securities mix, AFS unrealized loss vs net worth, borrowings, benefit-plan funding assets
- [x] National peer-group percentiles (NCUA peer groups)
- [x] Product-fit scoring from `config/products.yaml` with reasons you can read
- [x] Territory map, ranked targets, per-CU view, Today list
- [x] Local pipeline (stage, next action, notes) in `data/private/`
- [x] Salesforce CSV import with fuzzy name + state matching to NCUA charters

## v1: once Phil has internal data
- [ ] **Client list** → `data/private/clients.csv` (`cu_number` column). Hides current clients as prospects; later, a cross-sell view
- [x] Fee **structure** aligned to ALM First Form ADV 2A (fixed annual advisory fees, asset-based discretionary). Levels are still estimates
- [ ] **Salesforce report columns**: lock the import mapping, and bring in owner, last activity and open opportunities
- [ ] Confirm the product definitions (CPST especially; see below)

## v2: triggers and outreach
- [ ] Quarter-over-quarter triggers ("deposits fell 6% QoQ", "crossed $5B", "net worth under 8%") as a weekly "reasons to call" digest
- [ ] Growth path to $10B: project which CUs cross the CPST threshold within 2 to 3 years
- [ ] One-page call prep per CU (balance sheet story, peer gaps, suggested pitch)
- [ ] Email drafts per product and trigger
- [ ] Merger watch (NCUA merger notices) and conference and league events by state

## Assumptions to confirm (Phil)
1. **CPST = Capital Planning & Stress Testing** (NCUA Part 702 Subpart C: required at $10B+). Resolved from public sources.
   NCUA requires capital planning and stress testing for "covered" credit unions with $10B+ in assets. The scoring treats $10B+ as required
   and $5B to $10B as the prep market.
2. **Discretionary management** targets CUs that already fund benefit plans (split-dollar / collateral-assignment life insurance, 5300
   accounts NV0170/NV0173), plus CUs with room for a charitable donation account (CDA). A CDA is capped at 5% of net worth.
3. **Model validation** is aimed at $250M+ CUs. Larger and more mortgage-heavy CUs score higher.
4. Every threshold and fee in `products.yaml` is a first guess. Tune them together.
5. Territory = FL, GA, AL, MS, TN, SC, NC, AR, LA, KY, VA, with a $50M minimum.

## Known data caveats
- Map points use ZIP/city centroids, not street addresses. They are good at the territory level only.
- NCUA recoded parts of the 5300 in 2022. Legacy codes (703, 704A, 799D, 945, 789A) are blank, so the loader uses the new AS/NV/RL codes.
- Income is year-to-date in the 5300. ROA is annualized by quarter month.

# GitHub Actions — weekly for-sale registry

Two related pieces:

| Piece | Where | What it does |
|-------|--------|----------------|
| **Cursor skill** | `.cursor/skills/weekly-island-property-discovery/SKILL.md` | Already in the repo. In Cursor, ask to *run the weekly island property discovery skill* — sub-agents search brokers, then scripts update the map. |
| **GitHub Action** | `.github/workflows/main.yml` | Refreshes `docs/FOR-SALE-ISLANDS.md` and the registry every Monday (no broker research in CI). |

**Status:** Workflow is live on `main` (commit `929d7e6`).

### Run it now

1. Open **https://github.com/Drummond1/britishislands/actions/workflows/main.yml**
2. Click **Run workflow** → branch `main` → **Run workflow**
3. Open the run → confirm job **refresh-registry** succeeds.

### One-time permission check

**Settings → Actions → General → Workflow permissions** → **Read and write permissions** → Save.  
(Without this, the auto-commit step at the end of the job will fail.)

---

## Add the workflow on GitHub (only if missing)

Skip this section if `.github/workflows/main.yml` already exists on GitHub.

---

## Original manual setup (≈3 minutes)

1. Open your repo: **https://github.com/Drummond1/britishislands**
2. Go to **Actions** → **New workflow** → **set up a workflow yourself** (or **Create new workflow**).
3. Name the file:  
   `main.yml`  
   (under `.github/workflows/` — any `*.yml` name works; this repo uses `main.yml`).
4. Delete the template contents and paste the YAML from the next section.
5. Click **Commit changes…** → commit to `main`.
6. **Settings** → **Actions** → **General** → **Workflow permissions** → choose **Read and write permissions** → Save.  
   (Required so the job can commit registry updates.)
7. Test: **Actions** → **Weekly property discovery** → **Run workflow** → **Run workflow**.

After the first run, check **Actions** for a green run. If the registry changed, you’ll see a commit like `chore: weekly for-sale island registry refresh`.

---

## YAML to paste

Copy everything below into the new workflow file:

```yaml
name: Weekly property discovery

on:
  schedule:
    # Mondays 06:00 UTC
    - cron: "0 6 * * 1"
  workflow_dispatch:

permissions:
  contents: write

jobs:
  refresh-registry:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Refresh for-sale registry and docs
        run: |
          python3 scripts/run_property_discovery_weekly.py --registry-only

      - name: Commit registry updates if changed
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add docs/FOR-SALE-ISLANDS.md \
            data/discovery/property_listings_registry.json \
            data/for_sale_islands_summary.json
          if git diff --staged --quiet; then
            echo "No registry changes"
          else
            git commit -m "chore: weekly for-sale island registry refresh"
            git push
          fi
```

The same file lives locally at  
`.github/workflows/main.yml`.

---

## What runs when

| Trigger | Behaviour |
|---------|-----------|
| **Cron** (Mon 06:00 UTC) | Rebuilds registry + `FOR-SALE-ISLANDS.md` from current `islands.json` / verified manifest. |
| **workflow_dispatch** | Same, on demand from the Actions tab. |

**Not included in CI:** broker web research (Tier 4). That still needs the **Cursor skill** weekly so sub-agents can search obscure sites and update `property_tier4_obscure_raw.json`, then:

```bash
python3 scripts/run_property_discovery_weekly.py --apply-tier4
git add … && git commit && git push
```

---

## Optional: push workflows from Cursor later

Re-authenticate GitHub in Cursor with **`workflow`** scope, or use SSH/`gh` with a PAT that includes `workflow`. Then a normal push of `.github/workflows/property-discovery-weekly.yml` will work.

---

## Quick links

- Full island list: [`FOR-SALE-ISLANDS.md`](FOR-SALE-ISLANDS.md)
- Pipeline detail: [`PROPERTY-LISTINGS.md`](PROPERTY-LISTINGS.md)
- Cursor skill: [`.cursor/skills/weekly-island-property-discovery/SKILL.md`](../.cursor/skills/weekly-island-property-discovery/SKILL.md)

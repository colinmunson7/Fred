# Fred (Fake Reddit)

A phone-first newsfeed that replaces Reddit: about 25 headlines per edition from
chosen sites, forums, Bluesky accounts and YouTube channels, plus a short news
briefing. No comments, no algorithm, no infinite scroll. It ends with
"You're caught up."

A new edition is built every morning (about 5am Pacific) and evening (about 5pm Pacific), with backup runs in case GitHub starts late.

## What's in here

| File | What it does |
| --- | --- |
| `sources.yaml` | Every source, the 9 topic areas, feed rules (25 a day, max 5 per topic) and the "caught up" suggestions. **This is Fred's settings screen.** |
| `scripts/build.py` | Pulls every feed, picks the edition's headlines and writes `site/data.json`. |
| `site/index.html` | The newspaper-style front page you open on your phone. |
| `.github/workflows/build.yml` | Tells GitHub to build a new edition twice a day and publish the site. |
| `data/history.json` | What Fred has already shown, so headlines don't repeat. Updated automatically. |
| `tests/` | Checks that each edition follows the PRD's rules. |

## One-time setup (about 10 minutes, on your laptop)

1. **Create the repository.** On GitHub, click **New repository**. Name it `fred`,
   set it to **Public** (free hosting needs that), and create it.
2. **Upload the files.** On the new repo's page, click **uploading an existing file**
   and drag in everything from this folder.
   - Hidden folders like `.github` sometimes don't upload by drag-and-drop. If the
     **Actions** tab shows no "Build Fred" workflow afterwards, create the file
     by hand: **Add file → Create new file**, name it `.github/workflows/build.yml`,
     and paste in the contents of that file.
3. **Let the workflow save its history.** **Settings → Actions → General →
   Workflow permissions**, choose **Read and write permissions**, and save.
4. **Turn on the website.** **Settings → Pages → Build and deployment → Source:
   GitHub Actions.**
5. **Build the first edition.** **Actions → Build Fred → Run workflow.** It takes
   about a minute. When it finishes, the run page shows your site's address,
   something like `https://YOUR-USERNAME.github.io/fred/`.
6. **Put it on your phone.** Open that address in your phone's browser, then
   **Share → Add to Home Screen**. Fred now opens like an app.

## Changing sources

Ask Claude to edit `sources.yaml` (add a site, move a Bluesky account to another
topic, change the post count), or edit it on GitHub yourself. Saving the file
rebuilds the site automatically.

At the bottom of every edition, **Sources this edition** lists which feeds worked.
A source marked unavailable is usually a site that blocks automated readers;
those were flagged `verify: true` during planning.

## Running it on a computer (optional)

```bash
pip install -r requirements.txt pytest
python scripts/build.py            # build an edition from live feeds
python -m pytest tests             # check the feed rules
```

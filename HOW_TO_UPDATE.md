# How to update your profile

You never edit `README.md` by hand. You edit two data files, push, and a GitHub Action rebuilds the README for you (about 30 seconds).

| To change…                                  | Edit           |
| ------------------------------------------- | -------------- |
| Name, title, about me, links, tech stack    | `profile.yml`  |
| Projects                                    | `projects.yml` |
| Layout / section order                      | `templates/README.md.j2` |

Look for `# TODO` comments — those are placeholders to replace.

---

## Add a project

1. Open `projects.yml`.
2. Copy an existing block (from `- name:` down to `order:`) and paste it at the end.
3. Edit the fields:

```yaml
  - name: Expense Tracker
    description: Helps small teams cut monthly reporting time by 80%
    tech: [Python, FastAPI, React, PostgreSQL]
    repo: https://github.com/larzuaga11/expense-tracker
    demo: https://expense.example.com      # optional
    image: assets/projects/expense.png     # optional
    featured: true                         # big card (true) or "More projects" list (false)
    order: 3                               # lower = shown first
```

4. Commit and push. You can do this right on github.com: open the file, click the pencil ✏️, edit, then **Commit changes**.

**Writing tips for recruiters:** start the description with what the project *does* or *improved*, use numbers when you can, and keep it to one line.

### Add a screenshot

Drop a PNG/JPG/GIF into `assets/projects/` (around 1200×675 looks best) and set `image: assets/projects/your-file.png`. If the file isn't there, the build will stop and tell you.

---

## Tech badges

Write tech names normally (`Python`, `Node.js`, `AWS`). Common ones have logos and brand colors built in — see `TECH_LOGOS` near the top of `scripts/build_readme.py`. If a logo doesn't appear for a new tech, add a line there:

```python
"supabase": ("supabase", "3FCF8E"),   # name in lowercase: (slug, hex color)
```

Find slugs and colors at [simpleicons.org](https://simpleicons.org).

---

## First-time setup

1. On GitHub, create a **public** repo named exactly **`larzuaga11`** (same as your username). GitHub shows its README on your profile.
2. Push these files to its `main` branch:

   ```bash
   git remote add origin https://github.com/larzuaga11/larzuaga11.git
   git push -u origin main
   ```

3. Open the repo's **Actions** tab and confirm "Build README" ran with a green check.

## Preview locally (optional)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/build_readme.py
```

---

## Troubleshooting

- **The Action failed with a ❌ message** — open the failed run; the last line names the file, project, and field to fix (often a missing `description` or a YAML indentation slip).
- **Action can't push (`403`)** — repo **Settings → Actions → General → Workflow permissions** → choose **Read and write permissions**.
- **Stats cards show an error or don't load** — they come from the free public `github-readme-stats` service, which is sometimes rate-limited. It usually recovers on its own. For full reliability you can deploy your own copy to Vercel (instructions in that project's README) and change the `rs = ...` URL in `scripts/build_readme.py`. To hide stats, set `theme.show_stats: false`.
- **Change the accent color** — set `theme.accent` in `profile.yml` (6-digit hex, no `#`).

# Daily Deep Dive (3D)

A free daily blog, hosted on GitHub Pages, at
https://awesomelyinnovatingai.github.io/daily-deep-dive/

## How a post gets published

Each morning's briefing is exported from its doc as two Markdown files (the Briefing tab and the References tab), then:

```bash
python3 scripts/convert_briefing.py Briefing.md References.md --field "Technology"
git add _posts && git commit -m "Briefing for <date>" && git push
```

GitHub Pages rebuilds the site about a minute after each push.

## Layout

| Path | What it is |
| --- | --- |
| `_posts/` | One Markdown file per briefing, named `YYYY-MM-DD-title.md` |
| `_layouts/` | Page templates (site frame, post page) |
| `assets/css/site.css` | All styling, including dark mode |
| `index.html`, `archive.html`, `about.md` | Home, archive and About pages |
| `scripts/convert_briefing.py` | Turns an exported briefing into a post |

## Custom domain (optional)

Buy a domain, add it under Settings → Pages → Custom domain, then in `_config.yml` set `url` to the domain and `baseurl` to `""`.

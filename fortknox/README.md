# High Slot

Every NHL game scored shot by shot with a full-data expected-goals model, at
[highslot.web.app](https://highslot.web.app). It replaces the
single-page game sheets that used to live at `lknox.web.app/xgcalc/sheets.html`
(that URL now redirects here).

## How it fits together

1. `.github/workflows/xg-game-sheets.yml` runs every 20 minutes on game days.
   It fetches newly final games, scores every shot (`pipeline/nhl_sheets.py`) and
   force-pushes the JSON to the orphan branch `xg-sheets-data`.
2. It then dispatches `.github/workflows/fortknox-deploy.yml`, which copies that
   branch into `data/`, builds this site as a static export and deploys the
   `fortknox` hosting target.

Every team and player and every game of the current season has its own
pre-rendered page:

| Route | Page |
|---|---|
| `/`, `/games/<season>` | All games as mini box scores |
| `/game/<id>` | Recap, line score, shot map, xG race, stars, chances, scoring, rosters |
| `/game/archive` | The same page drawn in the browser for older seasons' games, which `firebase.json` rewrites to it |
| `/teams/<season>` | Standings (league, conference, division, wild card) and team lenses |
| `/team/<season>/<abbrev>` | A team over the season or its last 20, 10 or 5 games |
| `/players/<season>` | Skater and goalie tables |
| `/player/<id>` | A player's season: shot map (season or last 20, 10, 5 games), WOWY, game-by-game trend, game log |
| `/compare?p=<id>,<id>` | Up to four skaters or goalies side by side, with league percentiles; loads `/data/<season>/players.json` |
| `/regression/<season>` | Teams, shooters, on-ice results and goalies furthest ahead of or behind their xG |
| `/model` | How the xG model works, with live accuracy and calibration |
| `/about` | What the site is, glossary, credits |
| `/data/<season>/games.json` | Every game of a season; the games pages load it on demand |
| `/data/<season>/players.json` | A season's skater and goalie tables, for the compare page |
| `/data/<season>/game/<id>.json` | An older season's game sheet, loaded by `/game/archive` |

## Develop

```sh
./scripts/fetch-data.sh   # copy the published sheets into data/
npm install
npm run dev
```

`npm run build` writes the static site to `out/`. Builds are deterministic
(fixed build id), so a deploy only uploads pages whose content changed.

Before each build, `scripts/og-images.tsx` (the `prebuild` script) draws the
share cards into `public/og/` with Satori and resvg: one per game of the
current season, which a link to `/game/<id>` unfurls with (score, xG split,
date), and `site.png` for every other page and for older games.

Team pages show 5v5 forward lines, defence pairs and with-or-without-you
from `lines.json`; player pages add on-ice/off-ice numbers, WOWY and a season
shot map. Seasons published before October 2026 have no `lines.json` until
they are rebuilt (run the sheets workflow by hand with that season), and
those sections stay hidden for them.

Team logos are the NHL's dark-background SVGs, copied into `public/logos/`
so the site doesn't depend on `assets.nhle.com` at view time.

## Design

The [Inset Dark](https://better-design.com/design-systems/inset-dark) design
system, installed into `components/ui/` with
`npx shadcn@latest add -y -o https://better-design.com/registry/inset-dark/all.json`,
plus a High Slot layer in `app/globals.css`: navy-tinted surfaces like ice
under arena lights, Barlow Condensed capitals for headlines and the brand, and
one accent, ice cyan, for the logo, the active section, the winning score and
the first star. Away teams are red and home teams periwinkle.

The site was called Fort Knox until October 2026. The folder, the deploy
workflow (`fortknox-deploy.yml`) and the Firebase hosting target (`fortknox`,
now pointing at the `highslot` site) keep the old name.

`components/ui/` is vendored and skipped by ESLint; one type fix was needed in
`toggle-group.tsx`.

# Fort Knox

Every NHL game scored shot by shot with a full-data expected-goals model, at
[fortknox-hockey.web.app](https://fortknox-hockey.web.app). It replaces the
single-page game sheets that used to live at `lknox.web.app/xgcalc/sheets.html`
(that URL now redirects here).

## How it fits together

1. `.github/workflows/xg-game-sheets.yml` runs every 20 minutes on game days.
   It fetches newly final games, scores every shot (`pipeline/nhl_sheets.py`) and
   force-pushes the JSON to the orphan branch `xg-sheets-data`.
2. It then dispatches `.github/workflows/fortknox-deploy.yml`, which copies that
   branch into `data/`, builds this site as a static export and deploys the
   `fortknox` hosting target.

Every game, team and player has its own pre-rendered page:

| Route | Page |
|---|---|
| `/`, `/games/<season>` | All games as mini box scores |
| `/game/<id>` | Recap, line score, shot map, xG race, stars, chances, scoring, rosters |
| `/teams/<season>` | Standings (league, conference, division, wild card) and team lenses |
| `/team/<season>/<abbrev>` | A team over the season or its last 20, 10 or 5 games |
| `/players/<season>` | Skater and goalie tables |
| `/player/<id>` | A player's season and game log |
| `/model` | How the xG model works |

## Develop

```sh
./scripts/fetch-data.sh   # copy the published sheets into data/
npm install
npm run dev
```

`npm run build` writes the static site to `out/`. Builds are deterministic
(fixed build id), so a deploy only uploads pages whose content changed.

## Design

The [Inset Dark](https://better-design.com/design-systems/inset-dark) design
system, installed into `components/ui/` with
`npx shadcn@latest add -y -o https://better-design.com/registry/inset-dark/all.json`,
plus a "bullion" vault layer in `app/globals.css`: gold for the logo, the
active section, the winning score and the first star. Away teams are coral and
home teams blue, as on the old sheets.

`components/ui/` is vendored and skipped by ESLint; one type fix was needed in
`toggle-group.tsx`.

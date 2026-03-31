# Firebase Configuration Fix

## Problem
The Firebase rewrite rule is catching ALL requests (including JSON files) and redirecting them to `/index.html`, which is why the NHL lines page can't load `latest_analysis.json`.

## Solution

Replace the `firebase.json` file at `/Users/lucknox/Desktop/projects/firebase.json` with this:

```json
{
  "hosting": {
    "public": "build",
    "ignore": [
      "firebase.json",
      "**/.*",
      "**/node_modules/**"
    ],
    "rewrites": [
      {
        "source": "**",
        "destination": "/index.html"
      }
    ]
  }
}
```

**The issue:** Firebase's rewrite rules apply AFTER checking if a file exists. So the current config should work, but there might be a deployment issue.

## Alternative Fix (if above doesn't work)

Change the rewrite to be more specific:

```json
{
  "hosting": {
    "public": "build",
    "ignore": [
      "firebase.json",
      "**/.*",
      "**/node_modules/**"
    ],
    "rewrites": [
      {
        "source": "!**/*.{js,css,json,png,jpg,jpeg,gif,svg,ico,woff,woff2,ttf,eot,html}",
        "destination": "/index.html"
      }
    ]
  }
}
```

This explicitly excludes static files from the rewrite.

## Steps to Fix

1. Update `/Users/lucknox/Desktop/projects/firebase.json` with the alternative fix above
2. Redeploy:
   ```bash
   cd ~/Desktop/projects
   firebase deploy --only hosting
   ```

## Quick Test

After deploying, test the JSON file directly:
https://projects-brawlstars.web.app/nhllines/latest_analysis.json

If you see JSON data, it's working. If you see HTML, the rewrite is still catching it.

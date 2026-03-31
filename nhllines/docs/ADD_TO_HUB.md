# Adding NHL Lines to Your Project Hub

## ✅ Automatic Method (Recommended)

Your project hub automatically pulls from GitHub repos. To make NHL Lines appear:

1. Go to https://github.com/totqro/nhllines
2. Click the gear icon ⚙️ next to "About" (top right)
3. Add these topics:
   - `completed` ← This makes it show in the Completed tab!
   - `python`
   - `sports-betting`
   - `nhl`
4. Add website: `https://projects-brawlstars.web.app/nhllines/`
5. Add description: "NHL +EV Betting Finder - Statistical analysis for positive expected value bets"
6. Save changes

The repo will automatically appear in your project hub within a few seconds!

## 🔗 Navigation Links

### NHL Lines → Project Hub
✅ Already added! There's a "← Back to Projects" link at the top of the NHL Lines page.

### Project Hub → NHL Lines
✅ Will appear automatically once you add the `completed` topic to your GitHub repo!

The project card will show:
- Project name: nhllines
- Description: NHL +EV Betting Finder
- Language: Python
- Status badge: "Completed"
- Links: GitHub and Live site

## 🎨 Optional: Add Featured Project Banner

If you want to highlight NHL Lines on your project hub homepage, you can add a featured section.

Edit `~/Desktop/projects/src/Views/HomePage.js` and add this after the header:

```jsx
{/* Featured Project */}
<div className="featured-project">
  <h2>🏒 Featured: NHL +EV Betting Finder</h2>
  <p>Live statistical analysis for finding positive expected value NHL bets</p>
  <a href="/nhllines/" className="featured-link">View Dashboard →</a>
</div>
```

And add this to `~/Desktop/projects/src/Views/HomePage.css`:

```css
.featured-project {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  padding: 30px;
  border-radius: 12px;
  margin-bottom: 30px;
  text-align: center;
}

.featured-project h2 {
  margin-bottom: 10px;
}

.featured-link {
  display: inline-block;
  margin-top: 15px;
  padding: 10px 20px;
  background: white;
  color: #667eea;
  text-decoration: none;
  border-radius: 8px;
  font-weight: 600;
  transition: transform 0.2s;
}

.featured-link:hover {
  transform: translateY(-2px);
}
```

## 🚀 Deploy Changes

After making any changes, run:

```bash
cd ~/Desktop/nhllines
./build_and_deploy.sh
```

This will update everything and deploy to Firebase!

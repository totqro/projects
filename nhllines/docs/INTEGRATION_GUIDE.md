# NHL Lines Integration Guide

## ✅ Step 1: Files Copied to Projects Folder

Your NHL betting dashboard has been copied to:
```
~/Desktop/projects/public/nhllines/
```

The files are now part of your Firebase project and will be accessible at:
```
https://your-firebase-site.web.app/nhllines/
```

## 📋 Step 2: Add to GitHub (to show in Completed tab)

Your project hub reads from GitHub repos and uses **topics** to categorize them. To make NHL Lines appear in the "Completed" tab:

### Option A: Create a new GitHub repo for nhllines

1. Go to GitHub and create a new repository called `nhllines`

2. In your nhllines folder, initialize git:
   ```bash
   cd ~/Desktop/nhllines
   git init
   git add .
   git commit -m "Initial commit: NHL +EV Betting Finder"
   ```

3. Connect to GitHub and push:
   ```bash
   git remote add origin https://github.com/YOUR_USERNAME/nhllines.git
   git branch -M main
   git push -u origin main
   ```

4. **Add the "completed" topic to your repo:**
   - Go to your repo on GitHub
   - Click the gear icon ⚙️ next to "About"
   - In the "Topics" field, add: `completed`
   - Optionally add: `python`, `sports-betting`, `nhl`, `data-analysis`
   - Click "Save changes"

5. Add the live URL to your repo:
   - In the same "About" section
   - Add website: `https://your-firebase-site.web.app/nhllines/`

### Option B: Add as a manual project card

If you don't want to create a GitHub repo, you can manually add it to your project hub by modifying the HomePage.js to include static projects.

## 🚀 Step 3: Deploy to Firebase

1. Build your React app:
   ```bash
   cd ~/Desktop/projects
   npm run build
   ```

2. Deploy to Firebase:
   ```bash
   firebase deploy
   ```

3. Your NHL Lines dashboard will be live at:
   ```
   https://projects-brawlstars.web.app/nhllines/
   ```

## 🔄 Step 4: Update Data Regularly

To keep your betting analysis fresh:

### Manual Update:
```bash
cd ~/Desktop/nhllines
python3 main.py --stake 0.50 --conservative
cp latest_analysis.json ~/Desktop/projects/public/nhllines/
cd ~/Desktop/projects
npm run build
firebase deploy
```

### Automated Update (Optional):
Create a script `~/Desktop/nhllines/update_and_deploy.sh`:

```bash
#!/bin/bash
cd ~/Desktop/nhllines
python3 main.py --stake 0.50 --conservative
cp latest_analysis.json ~/Desktop/projects/public/nhllines/
cd ~/Desktop/projects
npm run build
firebase deploy --only hosting
```

Then add to crontab to run every 2 hours:
```bash
crontab -e
# Add this line:
0 */2 * * * /bin/bash ~/Desktop/nhllines/update_and_deploy.sh
```

## 📝 Notes

- The web dashboard reads from `latest_analysis.json`
- Your API keys stay secure in the backend (not exposed in web files)
- The dashboard auto-refreshes every 5 minutes when open
- Make sure to run the analysis before deploying to have fresh data

## 🎯 Quick Test

Test locally before deploying:
```bash
cd ~/Desktop/projects
npm start
```

Then visit: `http://localhost:3000/nhllines/`

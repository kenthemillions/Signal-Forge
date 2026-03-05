# Deploy Signal Forge to Render

## How Render gets your updates

Render deploys from **GitHub**. It does not see your local Cursor files until you push.

1. **Push from Cursor (or your machine) to GitHub**
   - In terminal: `git add -A && git commit -m "Your message" && git push origin main`
   - Or use Cursor’s Source Control (Ctrl+Shift+G), stage, commit, then **Push**

2. **Render auto-deploys**
   - If “Auto-Deploy” is on (default), Render builds and deploys on every push to `main`.
   - Dashboard: https://dashboard.render.com → your **signal-forge** service → **Events** to see deploy status.

3. **Manual deploy (optional)**
   - Render dashboard → your service → **Manual Deploy** → **Deploy latest commit**.

## After pushing

- First load can take 30–60 seconds on free tier (cold start). Then the site should load normally.
- If the app still shows “Loading…”, use **Refresh** on the dashboard or reload the page after the server is up.

## Environment on Render

- Set **SESSION_SECRET** in the service **Environment** tab (required for login).
- **DATABASE_URL** is set automatically if you linked a Postgres DB from the Render dashboard.

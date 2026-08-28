# Deploy Intellect to Google Cloud App Engine

## Step 1: Install Google Cloud SDK
Download and install from: https://cloud.google.com/sdk/docs/install

## Step 2: Login and Set Project
Open PowerShell or CMD and run:
```powershell
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

## Step 3: Update Environment Variables
Edit `app.yaml` and replace:
- `GROQ_API_KEY` with your actual Groq API key
- `SECRET_KEY` with a random string

## Step 4: Deploy
From the `d:\Student_prep\Intellect` folder, run:
```powershell
gcloud app deploy
```

## Step 5: Get Your URL
After deployment, your URL will be:
```
https://YOUR_PROJECT_ID.REGION_ID.r.appspot.com
```

Or run:
```powershell
gcloud app browse
```

## Step 6: Configure Mobile App
Your API base URL will be:
```
https://YOUR_PROJECT_ID.REGION_ID.r.appspot.com/api/v1
```

Update `lib/config.dart` with this URL, then rebuild the APK.

## Notes
- Free tier: 28 instance hours/day, 1GB outbound bandwidth/day
- The app stays awake (no sleep)
- Database (SQLite) persists on the instance disk but will reset if the instance restarts. For production, use Cloud SQL.

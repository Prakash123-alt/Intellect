# Deploy Intellect to PythonAnywhere (Free)

## Step 1: Sign Up
- Go to https://www.pythonanywhere.com
- Sign up for a free account

## Step 2: Upload Code
1. Open **Files** tab
2. Create folder: `Intellect`
3. Upload all your project files from `d:\Student_prep\Intellect` into `/home/YOUR_USERNAME/Intellect/`
   - app.py
   - api.py
   - pipeline.py
   - exam_platform.py
   - rag.py
   - media_notes.py
   - youtube_notes.py
   - requirements.txt
   - wsgi.py
   - templates/ folder
   - uploads/ folder (if you want to keep existing data, otherwise it will auto-create)
4. Upload `requirements.txt`

## Step 3: Create Virtual Environment
1. Open **Consoles** → **Bash**
2. Run:
```bash
cd ~/Intellect
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Step 4: Create Web App
1. Go to **Web** tab
2. Click **Add a new web app**
3. Choose **Manual configuration** (not Flask quickstart)
4. Choose **Python 3.11**
5. Set:
   - **Source code:** `/home/YOUR_USERNAME/Intellect`
   - **Working directory:** `/home/YOUR_USERNAME/Intellect`
   - **WSGI configuration file:** `/var/www/YOUR_USERNAME_pythonanywhere_com_wsgi.py` (upload the provided wsgi.py contents to this file)
   - **Virtualenv:** `/home/YOUR_USERNAME/Intellect/venv`

## Step 5: Configure WSGI File
In your WSGI config (`/var/www/YOUR_USERNAME_pythonanywhere_com_wsgi.py`), replace contents with:
```python
import sys
import os

path = '/home/YOUR_USERNAME/Intellect'
if path not in sys.path:
    sys.path.append(path)

os.environ['GROQ_API_KEY'] = 'YOUR_GROQ_API_KEY_HERE'
os.environ['SECRET_KEY'] = 'YOUR_SECRET_KEY_HERE'

from app import app as application
```

## Step 6: Set Environment Variables (Optional)
Alternatively, set env vars in PythonAnywhere dashboard under **Web → Environment variables**:
- `GROQ_API_KEY` = your key
- `SECRET_KEY` = any random string

## Step 7: Reload
Click the **Reload** button on the Web tab.

## Step 8: Get Your URL
Your API will be live at:
```
https://YOUR_USERNAME.pythonanywhere.com/api/v1/dashboard
```

## Step 9: Configure Mobile App
1. Open the mobile app
2. Go to **Settings** (or first-time setup)
3. Enter your URL: `https://YOUR_USERNAME.pythonanywhere.com/api/v1`

## Notes for Free Tier
- The web app goes to sleep after inactivity (30 min) and takes a few seconds to wake up on first request
- Max request time is limited to ~5 minutes
- ChromaDB and large file uploads may have issues due to free tier limits
- Database is stored in `/home/YOUR_USERNAME/Intellect/data/` by default

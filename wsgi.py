import sys
import os

# Replace YOUR_USERNAME with your actual PythonAnywhere username
PROJECT_DIR = '/home/YOUR_USERNAME/Intellect'

if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

os.chdir(PROJECT_DIR)

# app.py loads GROQ_API_KEY and SECRET_KEY from the .env file
from app import app as application

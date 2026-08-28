import sys
import os

# Add the project directory to the path
path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if path not in sys.path:
    sys.path.append(path)

# Set up environment variables (replace with your PythonAnywhere values)
os.environ['GROQ_API_KEY'] = os.getenv('GROQ_API_KEY', '')
os.environ['SECRET_KEY'] = os.getenv('SECRET_KEY', 'intellect-ai-exam-prep-2026')

# Import the Flask app
from app import app as application

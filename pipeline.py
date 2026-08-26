import sqlite3
import os
import json
import csv
import re
import time
import logging
from datetime import datetime, timedelta
from collections import Counter

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'qa_data.db')
EXPORT_DIR = os.path.join(os.path.dirname(__file__), 'exports')
LOG_DIR = os.path.join(os.path.dirname(__file__), 'logs')

# ─── Real-time Logging ───────────────────────────────────────────────
def _ensure_dirs():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    os.makedirs(EXPORT_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)

_ensure_dirs()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'pipeline.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('pipeline')


# ─── 1. Database Setup & Storage ─────────────────────────────────────
def init_db():
    _ensure_dirs()
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS qa_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        answer TEXT,
        model TEXT,
        response_time REAL,
        token_count INTEGER,
        keywords TEXT,
        topic TEXT,
        sentiment TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS stream_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT,
        event_type TEXT,
        data TEXT,
        processed INTEGER DEFAULT 0,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()
    logger.info("Database initialized")


def store_qa(question, answer, model, response_time, token_count=0):
    keywords = extract_keywords(question)
    topic = classify_topic(question)
    sentiment = detect_sentiment(question)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    c.execute('''INSERT INTO qa_logs 
        (question, answer, model, response_time, token_count, keywords, topic, sentiment)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
        (question, answer, model, response_time, token_count,
         json.dumps(keywords), topic, sentiment))
    conn.commit()
    conn.close()
    logger.info(f"Stored Q&A | Topic: {topic} | Keywords: {keywords[:3]} | Time: {response_time:.2f}s")


# ─── 2. Data Preprocessing & Cleaning ────────────────────────────────
def preprocess_text(text):
    if not text:
        return ""
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'[^\S\n]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()
    return text


def extract_keywords(text):
    stop_words = {'what', 'is', 'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for',
                  'of', 'and', 'or', 'but', 'how', 'why', 'when', 'where', 'who',
                  'can', 'do', 'does', 'will', 'are', 'was', 'were', 'be', 'been',
                  'have', 'has', 'had', 'it', 'its', 'this', 'that', 'with', 'from',
                  'i', 'me', 'my', 'you', 'your', 'we', 'they', 'them', 'about'}
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    return [w for w in words if w not in stop_words]


def classify_topic(text):
    topics = {
        'technology': ['ai', 'machine learning', 'deep learning', 'python', 'code',
                       'programming', 'software', 'algorithm', 'data', 'api', 'flutter',
                       'neural', 'model', 'computer', 'database', 'cloud', 'devops'],
        'science': ['physics', 'chemistry', 'biology', 'quantum', 'atom', 'molecule',
                    'experiment', 'theory', 'research', 'scientific', 'math', 'algebra'],
        'business': ['startup', 'saas', 'market', 'revenue', 'growth', 'strategy',
                     'product', 'customer', 'sales', 'finance', 'investment', 'profit'],
        'health': ['health', 'medical', 'disease', 'treatment', 'doctor', 'mental',
                   'exercise', 'nutrition', 'diet', 'sleep', 'wellness', 'fitness'],
        'education': ['learn', 'study', 'course', 'university', 'student', 'exam',
                      'teach', 'school', 'education', 'knowledge', 'training'],
        'ethics': ['ethics', 'moral', 'bias', 'fairness', 'privacy', 'responsible',
                   'regulation', 'policy', 'rights', 'society']
    }
    text_lower = text.lower()
    scores = {}
    for topic, keywords in topics.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[topic] = score
    return max(scores, key=scores.get) if scores else 'general'


def detect_sentiment(text):
    positive = ['good', 'great', 'best', 'love', 'amazing', 'excellent', 'helpful',
                'awesome', 'fantastic', 'wonderful', 'happy', 'thanks', 'please']
    negative = ['bad', 'worst', 'hate', 'terrible', 'awful', 'horrible', 'angry',
                'wrong', 'problem', 'issue', 'error', 'fail', 'broken']
    text_lower = text.lower()
    pos = sum(1 for w in positive if w in text_lower)
    neg = sum(1 for w in negative if w in text_lower)
    if pos > neg:
        return 'positive'
    elif neg > pos:
        return 'negative'
    return 'neutral'


# ─── 3. Analytics & Metrics ──────────────────────────────────────────
def get_analytics():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM qa_logs")
    total_queries = c.fetchone()[0]

    c.execute("SELECT AVG(response_time) FROM qa_logs WHERE response_time > 0")
    avg_response = c.fetchone()[0] or 0

    c.execute("SELECT SUM(token_count) FROM qa_logs")
    total_tokens = c.fetchone()[0] or 0

    c.execute("SELECT topic, COUNT(*) as cnt FROM qa_logs GROUP BY topic ORDER BY cnt DESC")
    topics = c.fetchall()

    c.execute("SELECT sentiment, COUNT(*) as cnt FROM qa_logs GROUP BY sentiment ORDER BY cnt DESC")
    sentiments = c.fetchall()

    c.execute("SELECT DATE(timestamp) as day, COUNT(*) FROM qa_logs GROUP BY day ORDER BY day DESC LIMIT 7")
    daily_usage = c.fetchall()

    c.execute("SELECT keywords FROM qa_logs WHERE keywords IS NOT NULL")
    all_keywords = []
    for row in c.fetchall():
        try:
            all_keywords.extend(json.loads(row[0]))
        except:
            pass
    top_keywords = Counter(all_keywords).most_common(10)

    c.execute("SELECT question, answer, topic, response_time, timestamp FROM qa_logs ORDER BY id DESC LIMIT 10")
    recent = c.fetchall()

    conn.close()

    return {
        'total_queries': total_queries,
        'avg_response_time': round(avg_response, 2),
        'total_tokens': total_tokens,
        'topics': topics,
        'sentiments': sentiments,
        'daily_usage': daily_usage,
        'top_keywords': top_keywords,
        'recent_queries': recent
    }


# ─── 4. Data Export for Model Training ────────────────────────────────
def export_training_data(format='json'):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    c.execute("SELECT question, answer, topic, keywords, sentiment FROM qa_logs")
    rows = c.fetchall()
    conn.close()

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    if format == 'json':
        filepath = os.path.join(EXPORT_DIR, f'training_data_{timestamp}.json')
        data = []
        for row in rows:
            data.append({
                'instruction': row[0],
                'output': row[1],
                'topic': row[2],
                'keywords': json.loads(row[3]) if row[3] else [],
                'sentiment': row[4]
            })
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    elif format == 'csv':
        filepath = os.path.join(EXPORT_DIR, f'training_data_{timestamp}.csv')
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['question', 'answer', 'topic', 'keywords', 'sentiment'])
            for row in rows:
                writer.writerow(row)

    logger.info(f"Exported {len(rows)} records to {filepath}")
    return filepath, len(rows)


# ─── 5. Real-time Stream Processing ──────────────────────────────────
def log_stream_event(source, event_type, data):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    c.execute('''INSERT INTO stream_events (source, event_type, data)
        VALUES (?, ?, ?)''', (source, event_type, json.dumps(data)))
    conn.commit()
    conn.close()
    logger.info(f"Stream event | Source: {source} | Type: {event_type}")


def process_pending_events():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    c.execute("SELECT id, source, event_type, data FROM stream_events WHERE processed = 0")
    events = c.fetchall()
    for event in events:
        eid, source, etype, data = event
        logger.info(f"Processing event #{eid}: {etype} from {source}")
        c.execute("UPDATE stream_events SET processed = 1 WHERE id = ?", (eid,))
    conn.commit()
    conn.close()
    return len(events)


def get_stream_stats():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM stream_events")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM stream_events WHERE processed = 0")
    pending = c.fetchone()[0]
    c.execute("SELECT source, COUNT(*) FROM stream_events GROUP BY source")
    sources = c.fetchall()
    conn.close()
    return {'total_events': total, 'pending': pending, 'sources': sources}


# Initialize on import
init_db()

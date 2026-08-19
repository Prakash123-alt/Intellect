# Intellect AI - Data Pipeline Documentation

## Overview

The Intellect AI Data Pipeline is a complete end-to-end system that handles data collection, preprocessing, storage, analytics, real-time streaming, and data export for model training. It is built on top of the Intellect AI Q&A application.

---

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  User Input  │────▶│ Preprocessing│────▶│   Groq API   │
│ (Web/Flutter)│     │  & Cleaning  │     │ (Qwen 27B)   │
└──────────────┘     └──────────────┘     └──────┬───────┘
                                                  │
                          ┌───────────────────────▼───────────────────────┐
                          │              PIPELINE CORE                    │
                          │                                               │
                          │  ┌─────────┐  ┌──────────┐  ┌─────────────┐  │
                          │  │ Storage │  │ Analytics│  │   Stream    │  │
                          │  │ (SQLite)│  │ & Metrics│  │  Processing │  │
                          
                          │  └─────────┘  └──────────┘  └─────────────┘  │
                          │                                               │
                          │  ┌─────────┐  ┌──────────┐  ┌─────────────┐  │
                          │  │ Export  │  │ Logging  │  │  Sentiment  │  │
                          │  │JSON/CSV │  │ Real-time│  │  Analysis   │  │
                          │  └─────────┘  └──────────┘  └─────────────┘  │
                          └───────────────────────────────────────────────┘
```

---

## Project Structure

```
simple-ai-app/
├── app.py                  # Flask backend with pipeline integration
├── pipeline.py             # Core data pipeline module
├── .env                    # API key (not pushed to GitHub)
├── requirements.txt        # Python dependencies
├── templates/
│   ├── index.html          # Q&A web interface
│   └── analytics.html      # Analytics dashboard
├── data/
│   └── qa_data.db          # SQLite database (auto-created)
├── exports/                # Training data exports (auto-created)
├── logs/
│   └── pipeline.log        # Real-time pipeline logs (auto-created)
└── PIPELINE_DOCS.md        # This documentation
```

---

## Pipeline Components

### 1. Data Collection & Storage (SQLite)

**File:** `pipeline.py` → `init_db()`, `store_qa()`

Every user query is stored in a SQLite database with rich metadata:

**Table: `qa_logs`**

| Column        | Type     | Description                           |
|---------------|----------|---------------------------------------|
| id            | INTEGER  | Auto-incrementing primary key         |
| question      | TEXT     | User's original question              |
| answer        | TEXT     | AI-generated response                 |
| model         | TEXT     | Model used (e.g., qwen/qwen3.6-27b)  |
| response_time | REAL     | API response time in seconds          |
| token_count   | INTEGER  | Total tokens consumed                 |
| keywords      | TEXT     | Extracted keywords (JSON array)       |
| topic         | TEXT     | Auto-classified topic                 |
| sentiment     | TEXT     | Detected sentiment                    |
| timestamp     | DATETIME | When the query was made               |

**Table: `stream_events`**

| Column      | Type     | Description                          |
|-------------|----------|--------------------------------------|
| id          | INTEGER  | Auto-incrementing primary key        |
| source      | TEXT     | Event source (web, flutter, api)     |
| event_type  | TEXT     | Type of event (query, error, etc.)   |
| data        | TEXT     | Event payload (JSON)                 |
| processed   | INTEGER  | 0 = pending, 1 = processed          |
| timestamp   | DATETIME | When the event occurred              |

**How it works:**
```python
store_qa(question, answer, model, response_time, token_count)
```
- Called automatically after every API response
- Extracts keywords, classifies topic, detects sentiment
- Stores everything in SQLite for future analysis

---

### 2. Data Preprocessing & Cleaning

**File:** `pipeline.py` → `preprocess_text()`, `extract_keywords()`, `classify_topic()`, `detect_sentiment()`

#### a) Text Preprocessing (`preprocess_text`)
- Removes `<think>...</think>` reasoning blocks from AI output
- Strips all HTML tags
- Normalizes whitespace

#### b) Keyword Extraction (`extract_keywords`)
- Tokenizes text into words (3+ characters)
- Removes common stop words (is, the, a, an, etc.)
- Returns list of meaningful keywords
- Example: "What is deep learning?" → `['deep', 'learning']`

#### c) Topic Classification (`classify_topic`)
- Rule-based classifier using keyword matching
- Supported topics:
  - **technology** — AI, programming, software, cloud
  - **science** — physics, chemistry, biology, math
  - **business** — startup, market, finance, strategy
  - **health** — medical, nutrition, fitness, wellness
  - **education** — learning, university, courses, exams
  - **ethics** — bias, fairness, privacy, policy
  - **general** — default if no topic matches

#### d) Sentiment Analysis (`detect_sentiment`)
- Keyword-based sentiment detection
- Returns: `positive`, `negative`, or `neutral`
- Positive words: good, great, amazing, excellent, etc.
- Negative words: bad, terrible, problem, error, etc.

---

### 3. Analytics & Metrics

**File:** `pipeline.py` → `get_analytics()`
**Route:** `GET /analytics`

The analytics dashboard provides:

| Metric             | Description                              |
|--------------------|------------------------------------------|
| Total Queries      | Total number of questions asked           |
| Avg Response Time  | Average Groq API response time            |
| Total Tokens       | Cumulative tokens used                    |
| Topic Distribution | Bar chart of questions per topic           |
| Top Keywords       | Most frequently used keywords (top 10)    |
| Sentiment Analysis | Breakdown of positive/neutral/negative    |
| Daily Usage        | Questions per day (last 7 days)           |
| Recent Queries     | Last 10 questions with metadata           |

---

### 4. Data Export for Model Training

**File:** `pipeline.py` → `export_training_data()`
**Routes:** `GET /export/json`, `GET /export/csv`

Exports all Q&A data in formats ready for model fine-tuning:

#### JSON Export Format (for LLM fine-tuning):
```json
[
  {
    "instruction": "What is deep learning?",
    "output": "Deep learning is a subset of machine learning...",
    "topic": "technology",
    "keywords": ["deep", "learning"],
    "sentiment": "neutral"
  }
]
```

#### CSV Export Format (for spreadsheet analysis):
```csv
question,answer,topic,keywords,sentiment
"What is deep learning?","Deep learning is...","technology","[\"deep\",\"learning\"]","neutral"
```

**Export directory:** `exports/training_data_YYYYMMDD_HHMMSS.json`

---

### 5. Real-time Stream Processing

**File:** `pipeline.py` → `log_stream_event()`, `process_pending_events()`, `get_stream_stats()`
**Route:** `GET /process-events`

Tracks events from multiple sources in real-time:

| Source  | Description                            |
|---------|----------------------------------------|
| web     | Queries from the Flask web interface   |
| flutter | Queries from the Flutter mobile app    |
| api     | Queries from direct API calls          |

**How it works:**
1. Every query logs a stream event with source, type, and data
2. Events are stored with `processed = 0` (pending)
3. `/process-events` endpoint marks all pending events as processed
4. Analytics dashboard shows total events, pending count, and source breakdown

**Real-time log file:** `logs/pipeline.log`
```
2026-08-18 15:06:42 | INFO | Database initialized
2026-08-18 15:07:01 | INFO | Stored Q&A | Topic: technology | Keywords: ['deep', 'learning'] | Time: 1.23s
2026-08-18 15:07:01 | INFO | Stream event | Source: web | Type: query
```

---

## API Endpoints

| Method | Endpoint          | Description                        |
|--------|-------------------|------------------------------------|
| GET    | `/`               | Q&A web interface                  |
| POST   | `/`               | Submit question (web form)         |
| POST   | `/api/ask`        | REST API for Flutter/external apps |
| GET    | `/analytics`      | Analytics dashboard                |
| GET    | `/export/json`    | Download training data as JSON     |
| GET    | `/export/csv`     | Download training data as CSV      |
| GET    | `/process-events` | Process pending stream events      |

### API Usage Example (`/api/ask`):

**Request:**
```json
POST /api/ask
Content-Type: application/json

{
  "question": "What is machine learning?"
}
```

**Response:**
```json
{
  "answer": "Machine learning is a branch of AI...",
  "response_time": 1.45
}
```

---

## Tech Stack

| Component       | Technology                |
|-----------------|---------------------------|
| Backend         | Python Flask              |
| AI Model        | Qwen 3.6 27B (via Groq)  |
| Database        | SQLite                    |
| Logging         | Python logging module     |
| Preprocessing   | Regex, NLP basics         |
| Analytics       | SQL aggregations          |
| Export Formats   | JSON, CSV                 |
| Mobile App      | Flutter (Dart)            |
| API Protocol    | REST (JSON over HTTP)     |

---

## How to Run

```bash
# 1. Activate virtual environment
aiapp\Scripts\activate

# 2. Install dependencies
pip install flask groq python-dotenv markdown

# 3. Set up API key in .env
GROQ_API_KEY=your_groq_api_key_here

# 4. Run the app
python app.py

# 5. Open in browser
# Q&A App:    http://127.0.0.1:5000
# Analytics:  http://127.0.0.1:5000/analytics
# Export:     http://127.0.0.1:5000/export/json
```

---

## Data Flow Diagram

```
                    ┌─────────────────────────────────────────┐
                    │           USER INTERACTION              │
                    │                                         │
                    │   Web Browser ──── Flutter App           │
                    │        │                │                │
                    └────────┼────────────────┼────────────────┘
                             │                │
                    ┌────────▼────────────────▼────────────────┐
                    │           FLASK BACKEND                  │
                    │                                         │
                    │   /           POST /api/ask              │
                    │   │               │                      │
                    │   └───────┬───────┘                      │
                    │           ▼                              │
                    │      ask_groq()                          │
                    │           │                              │
                    └───────────┼──────────────────────────────┘
                                │
              ┌─────────────────┼─────────────────────┐
              │                 │                     │
              ▼                 ▼                     ▼
    ┌──────────────┐  ┌──────────────┐     ┌──────────────┐
    │  Groq API    │  │  Pipeline    │     │   Stream     │
    │  (AI Model)  │  │  Storage     │     │   Logger     │
    │              │  │  (SQLite)    │     │              │
    └──────┬───────┘  └──────┬───────┘     └──────┬───────┘
           │                 │                     │
           ▼                 ▼                     ▼
    ┌──────────────┐  ┌──────────────┐     ┌──────────────┐
    │  Response    │  │  Analytics   │     │  Log File    │
    │  to User     │  │  Dashboard   │     │  pipeline.log│
    └──────────────┘  │  + Export    │     └──────────────┘
                      └──────────────┘
```

---

## Interview Explanation

> "I built a complete data pipeline for my AI Q&A application. Every user query goes through 5 stages:
>
> 1. **Data Collection** — stored in SQLite with metadata like response time, tokens, and timestamps.
> 2. **Preprocessing** — text cleaning, keyword extraction, and removal of AI reasoning artifacts.
> 3. **Analytics** — real-time topic classification, sentiment analysis, and usage metrics displayed on a dashboard.
> 4. **Export** — training-ready data export in JSON and CSV formats for potential model fine-tuning.
> 5. **Stream Processing** — event logging from multiple sources (web, mobile, API) with real-time monitoring.
>
> The pipeline processes data from both the Flask web app and the Flutter mobile app through a unified REST API."

---


## Future Improvements

- Replace SQLite with PostgreSQL for production scale
- Add Apache Kafka for real-time event streaming
- Implement model fine-tuning with exported data using Hugging Face
- Add user authentication and per-user analytics
- Deploy with Docker + Kubernetes for scalability
- Add A/B testing for different AI models
- Implement data drift detection for monitoring model performance

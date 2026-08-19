import sqlite3
import os
import json
import re
import time
import logging
from datetime import datetime, timedelta
from collections import Counter

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'qa_data.db')
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'uploads')

os.makedirs(UPLOAD_DIR, exist_ok=True)

logger = logging.getLogger('exam_platform')


# ─── Helpers ──────────────────────────────────────────────────────────

def _get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _parse_json_response(text):
    """Extract JSON from AI response, handling thinking tags and markdown code blocks."""
    logger.info(f"Raw AI response length: {len(text)}")

    # Step 1: Try to get content OUTSIDE thinking tags first
    stripped = re.sub(r'<think>[\s\S]*?</think>', '', text)
    stripped = re.sub(r'<\|think\|>[\s\S]*?<\|/think\|>', '', stripped)
    stripped = re.sub(r'<think>[\s\S]*$', '', stripped)
    stripped = stripped.strip()

    # Step 2: If nothing outside think tags, search for JSON INSIDE them
    if not stripped or not re.search(r'[\[\{]', stripped):
        logger.info("No content outside think tags, extracting JSON from within thinking")
        # Use the full original text to find JSON
        search_text = text
    else:
        search_text = stripped

    # Step 3: Extract JSON from the text
    json_text = _extract_json(search_text)

    # Step 4: Clean and parse
    json_text = re.sub(r',\s*(\]|\})', r'\1', json_text)
    json_text = re.sub(r'//[^\n]*', '', json_text)

    try:
        return json.loads(json_text)
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse failed: {e}")
        logger.error(f"Text being parsed (first 500 chars): {json_text[:500]}")
        lines = json_text.strip().split('\n')
        cleaned = '\n'.join(line for line in lines if line.strip())
        return json.loads(cleaned)


def _extract_json(text):
    """Find and extract the largest valid JSON array or object from text."""
    # Try code block first
    match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?\s*```', text)
    if match:
        candidate = match.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    # Use bracket matching to find the largest valid JSON structure
    candidates = []

    def find_bracket_matches(open_ch, close_ch):
        """Find all matching bracket ranges in text, respecting strings."""
        ranges = []
        for m in re.finditer(re.escape(open_ch), text):
            start = m.start()
            depth = 0
            in_string = False
            escape = False
            end = None
            for i in range(start, len(text)):
                ch = text[i]
                if escape:
                    escape = False
                    continue
                if ch == '\\' and in_string:
                    escape = True
                    continue
                if ch == '"' and not escape:
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == open_ch:
                    depth += 1
                elif ch == close_ch:
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            if end:
                ranges.append((start, end))
        return ranges

    # Collect candidates from both arrays and objects, ordered by size (largest first)
    for start, end in find_bracket_matches('[', ']'):
        candidates.append((start, end))
    for start, end in find_bracket_matches('{', '}'):
        candidates.append((start, end))

    # Sort by length descending - largest is most likely the top-level response
    candidates.sort(key=lambda x: x[1] - x[0], reverse=True)

    for start, end in candidates:
        candidate = text[start:end]
        # Remove trailing commas before final brackets
        cleaned = re.sub(r',\s*\]', ']', candidate)
        cleaned = re.sub(r',\s*\}', '}', cleaned)
        try:
            json.loads(cleaned)
            return cleaned
        except json.JSONDecodeError:
            continue

    # Fallback: regex approach
    match = re.search(r'(\[[\s\S]*\])', text)
    if not match:
        match = re.search(r'(\{[\s\S]*\})', text)
    if match:
        return match.group(1).strip()

    raise ValueError("No JSON structure found in AI response")


def _normalize_questions(data):
    """Normalize quiz questions into a list of dicts with expected keys."""
    # If it's a dict with a list inside, extract the list
    if isinstance(data, dict):
        logger.info(f"Quiz response is a dict with keys: {list(data.keys())}")
        # Try known keys first
        for key in ('questions', 'quiz', 'data', 'items', 'mcq', 'quiz_questions'):
            if key in data and isinstance(data[key], list):
                data = data[key]
                break
        if isinstance(data, dict):
            # Single question wrapped in a dict
            if 'question' in data:
                data = [data]
            else:
                # Try ANY list value in the dict
                for v in data.values():
                    if isinstance(v, list) and len(v) > 0:
                        data = v
                        break

    if not isinstance(data, list):
        raise ValueError(f"Expected a list of questions, got {type(data).__name__}: keys={list(data.keys()) if isinstance(data, dict) else 'N/A'}")

    questions = []
    for item in data:
        if isinstance(item, str):
            continue  # Skip stray strings
        if not isinstance(item, dict):
            continue
        # Normalize options format
        opts = item.get('options', {})
        if isinstance(opts, list) and len(opts) >= 4:
            opts = {'A': opts[0], 'B': opts[1], 'C': opts[2], 'D': opts[3]}
            item['options'] = opts
        elif isinstance(opts, dict):
            # Handle lowercase keys
            normalized = {}
            for k, v in opts.items():
                normalized[k.upper().strip()] = v
            item['options'] = normalized
        # Normalize correct answer
        if 'correct' in item:
            item['correct'] = str(item['correct']).strip().upper()[:1]
        elif 'answer' in item:
            item['correct'] = str(item['answer']).strip().upper()[:1]
        elif 'correct_answer' in item:
            item['correct'] = str(item['correct_answer']).strip().upper()[:1]

        # Reject placeholder/empty content
        qtext = str(item.get('question', '')).strip()
        if not qtext or qtext == '...' or len(qtext) < 5:
            continue
        opts = item.get('options', {})
        if not isinstance(opts, dict) or any(str(v).strip() in ('', '...') for v in opts.values()):
            continue

        if 'question' in item and 'correct' in item:
            questions.append(item)

    if not questions:
        raise ValueError("No valid questions found in AI response")

    return questions


def _normalize_flashcards(data):
    """Normalize flashcards into a list of dicts with front/back keys."""
    if isinstance(data, dict):
        for key in ('flashcards', 'cards', 'data', 'items'):
            if key in data and isinstance(data[key], list):
                data = data[key]
                break

    if not isinstance(data, list):
        raise ValueError(f"Expected a list of flashcards, got {type(data).__name__}")

    cards = []
    for item in data:
        if not isinstance(item, dict):
            continue
        # Handle alternate key names
        front = item.get('front') or item.get('question') or item.get('term', '')
        back = item.get('back') or item.get('answer') or item.get('definition', '')
        # Reject placeholder/empty content
        front = str(front).strip()
        back = str(back).strip()
        if not front or not back or front == '...' or back == '...' or len(front) < 3 or len(back) < 3:
            continue
        cards.append({
            'front': front,
            'back': back,
            'difficulty': item.get('difficulty', 'medium')
        })

    if not cards:
        raise ValueError("No valid flashcards found in AI response")

    return cards


def _ai_call(client, model, system_prompt, user_prompt, retries=2):
    """Make an AI call with retry on failure."""
    last_error = None
    for attempt in range(retries + 1):
        try:
            extra = "\n\nIMPORTANT: Return ONLY valid JSON. No thinking, no explanation, no markdown code blocks." if attempt > 0 else ""
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt + extra}
                ],
                temperature=0.7
            )
            raw = response.choices[0].message.content
            logger.info(f"AI call attempt {attempt + 1} succeeded, response length: {len(raw)}")
            return raw
        except Exception as e:
            last_error = e
            logger.error(f"AI call attempt {attempt + 1} failed: {e}")
            if attempt < retries:
                time.sleep(1)
    raise last_error


# ─── Database Setup ───────────────────────────────────────────────────

def init_exam_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS subjects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        description TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS pdfs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject TEXT,
        filename TEXT NOT NULL,
        original_name TEXT,
        extracted_text TEXT,
        page_count INTEGER DEFAULT 0,
        uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS flashcards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject TEXT,
        topic TEXT,
        front TEXT NOT NULL,
        back TEXT NOT NULL,
        difficulty TEXT DEFAULT 'medium',
        times_reviewed INTEGER DEFAULT 0,
        confidence INTEGER DEFAULT 0,
        last_reviewed DATETIME,
        next_review DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS quizzes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject TEXT,
        topic TEXT,
        difficulty TEXT DEFAULT 'medium',
        total_questions INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS quiz_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quiz_id INTEGER NOT NULL,
        question TEXT NOT NULL,
        option_a TEXT,
        option_b TEXT,
        option_c TEXT,
        option_d TEXT,
        correct_answer TEXT,
        explanation TEXT,
        FOREIGN KEY (quiz_id) REFERENCES quizzes(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS quiz_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quiz_id INTEGER NOT NULL,
        score INTEGER DEFAULT 0,
        total INTEGER DEFAULT 0,
        percentage REAL DEFAULT 0,
        time_taken REAL DEFAULT 0,
        answers TEXT,
        weak_topics TEXT,
        attempted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (quiz_id) REFERENCES quizzes(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS study_plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject TEXT,
        exam_date TEXT,
        hours_per_day REAL DEFAULT 2,
        plan_data TEXT,
        status TEXT DEFAULT 'active',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS study_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject TEXT,
        topic TEXT,
        duration_minutes INTEGER DEFAULT 0,
        activity_type TEXT,
        started_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject TEXT,
        title TEXT,
        content TEXT,
        source_type TEXT DEFAULT 'lecture',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS topic_mastery (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject TEXT,
        topic TEXT,
        mastery_level REAL DEFAULT 0,
        quiz_scores TEXT DEFAULT '[]',
        times_studied INTEGER DEFAULT 0,
        is_weak INTEGER DEFAULT 0,
        last_studied DATETIME,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject TEXT,
        prediction_data TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    conn.commit()
    conn.close()
    logger.info("Exam platform database initialized")


# ─── PDF Processing ──────────────────────────────────────────────────

def extract_pdf_text(filepath):
    """Extract text from a PDF file using PyMuPDF, falling back to PyPDF2."""
    # Try PyMuPDF first (much more robust)
    try:
        import pymupdf
        text = ""
        with pymupdf.open(filepath) as doc:
            page_count = len(doc)
            for page in doc:
                text += page.get_text() or ""
                text += "\n\n"
        extracted = text.strip()
        if extracted:
            logger.info(f"PyMuPDF extracted {len(extracted)} chars from {page_count} pages")
            return extracted, page_count
    except ImportError:
        logger.warning("PyMuPDF not installed, will try PyPDF2")
    except Exception as e:
        logger.warning(f"PyMuPDF extraction failed: {e}")

    # Fall back to PyPDF2
    try:
        import PyPDF2
        text = ""
        page_count = 0
        with open(filepath, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            page_count = len(reader.pages)
            for page in reader.pages:
                text += page.extract_text() or ""
                text += "\n\n"
        extracted = text.strip()
        if extracted:
            logger.info(f"PyPDF2 extracted {len(extracted)} chars from {page_count} pages")
            return extracted, page_count
    except Exception as e:
        logger.error(f"PyPDF2 extraction failed: {e}")

    return "", 0


def save_pdf(subject, filename, original_name, text, page_count):
    conn = _get_conn()
    c = conn.cursor()
    c.execute('''INSERT INTO pdfs (subject, filename, original_name, extracted_text, page_count)
        VALUES (?, ?, ?, ?, ?)''', (subject, filename, original_name, text, page_count))
    pdf_id = c.lastrowid
    conn.commit()
    conn.close()
    return pdf_id


def get_pdfs(subject=None):
    conn = _get_conn()
    c = conn.cursor()
    if subject:
        c.execute("SELECT * FROM pdfs WHERE subject = ? ORDER BY uploaded_at DESC", (subject,))
    else:
        c.execute("SELECT * FROM pdfs ORDER BY uploaded_at DESC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_pdf(pdf_id):
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM pdfs WHERE id = ?", (pdf_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


# ─── Flashcards ───────────────────────────────────────────────────────

def generate_flashcards(client, model, topic, count=10, context=None):
    """Generate flashcards using AI with retry on parse failure."""
    ctx = f"\n\nUse this study material as reference:\n{context[:3000]}" if context else ""
    prompt = f"""Generate exactly {count} flashcards on the topic "{topic}".{ctx}

Return a JSON array where each element has:
- "front": the question or term (concise)
- "back": the answer or definition (clear, 1-3 sentences)
- "difficulty": one of "easy", "medium", "hard"

Return ONLY the JSON array, no other text."""

    system = "You are an expert educator. Generate high-quality flashcards. Respond with ONLY a valid JSON array. Do not include any explanation, commentary, or thinking."

    for attempt in range(3):
        try:
            raw = _ai_call(client, model, system, prompt)
            result = _parse_json_response(raw)
            return _normalize_flashcards(result)
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(f"Flashcard generation parse attempt {attempt + 1} failed: {e}")
            if attempt == 2:
                raise
            time.sleep(0.5)


def save_flashcards(subject, topic, cards):
    conn = _get_conn()
    c = conn.cursor()
    now = datetime.now().isoformat()
    saved = 0
    for card in cards:
        c.execute('''INSERT INTO flashcards (subject, topic, front, back, difficulty, next_review)
            VALUES (?, ?, ?, ?, ?, ?)''',
            (subject, topic, card['front'], card['back'],
             card.get('difficulty', 'medium'), now))
        saved += 1
    conn.commit()
    conn.close()
    return saved


def get_flashcards(subject=None, topic=None):
    conn = _get_conn()
    c = conn.cursor()
    query = "SELECT * FROM flashcards WHERE 1=1"
    params = []
    if subject:
        query += " AND subject = ?"
        params.append(subject)
    if topic:
        query += " AND topic = ?"
        params.append(topic)
    query += " ORDER BY created_at DESC"
    c.execute(query, params)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_due_flashcards(limit=20):
    conn = _get_conn()
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute("""SELECT * FROM flashcards 
        WHERE next_review IS NULL OR next_review <= ?
        ORDER BY confidence ASC, next_review ASC LIMIT ?""", (now, limit))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def update_flashcard_review(card_id, confidence):
    """Update flashcard after review. Confidence: 1-5."""
    intervals = {1: 1, 2: 1, 3: 3, 4: 7, 5: 14}
    days = intervals.get(confidence, 1)
    next_review = (datetime.now() + timedelta(days=days)).isoformat()
    conn = _get_conn()
    c = conn.cursor()
    c.execute("""UPDATE flashcards SET 
        confidence = ?, times_reviewed = times_reviewed + 1,
        last_reviewed = ?, next_review = ?
        WHERE id = ?""", (confidence, datetime.now().isoformat(), next_review, card_id))
    conn.commit()
    conn.close()


def get_flashcard_stats():
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM flashcards")
    total = c.fetchone()[0]
    now = datetime.now().isoformat()
    c.execute("SELECT COUNT(*) FROM flashcards WHERE next_review IS NULL OR next_review <= ?", (now,))
    due = c.fetchone()[0]
    c.execute("SELECT AVG(confidence) FROM flashcards WHERE confidence > 0")
    avg_conf = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM flashcards WHERE confidence >= 4")
    mastered = c.fetchone()[0]
    conn.close()
    return {'total': total, 'due': due, 'avg_confidence': round(avg_conf, 1), 'mastered': mastered}


# ─── Quizzes ──────────────────────────────────────────────────────────

def generate_quiz(client, model, topic, difficulty='medium', count=10, context=None):
    """Generate quiz questions using AI with retry on parse failure."""
    ctx = f"\n\nBase questions on this material:\n{context[:3000]}" if context else ""
    prompt = f"""Generate exactly {count} multiple choice questions on "{topic}" at {difficulty} difficulty level.{ctx}

Return a JSON array where each element has:
- "question": the question text
- "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}}
- "correct": the correct option letter (A, B, C, or D)
- "explanation": brief explanation of the correct answer (1-2 sentences)

Return ONLY the JSON array, no other text."""

    system = "You are an expert exam question creator. Generate clear, unambiguous MCQ questions. Respond with ONLY a valid JSON array. Do not include any explanation, commentary, or thinking."

    for attempt in range(3):
        try:
            raw = _ai_call(client, model, system, prompt)
            result = _parse_json_response(raw)
            return _normalize_questions(result)
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(f"Quiz generation parse attempt {attempt + 1} failed: {e}")
            if attempt == 2:
                raise
            time.sleep(0.5)


def save_quiz(subject, topic, difficulty, questions):
    conn = _get_conn()
    c = conn.cursor()
    c.execute('''INSERT INTO quizzes (subject, topic, difficulty, total_questions)
        VALUES (?, ?, ?, ?)''', (subject, topic, difficulty, len(questions)))
    quiz_id = c.lastrowid
    for q in questions:
        opts = q.get('options', {})
        c.execute('''INSERT INTO quiz_questions 
            (quiz_id, question, option_a, option_b, option_c, option_d, correct_answer, explanation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (quiz_id, q['question'], opts.get('A', ''), opts.get('B', ''),
             opts.get('C', ''), opts.get('D', ''), q['correct'], q.get('explanation', '')))
    conn.commit()
    conn.close()
    return quiz_id


def get_all_quizzes():
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM quizzes ORDER BY created_at DESC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_quiz(quiz_id):
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,))
    quiz = c.fetchone()
    if not quiz:
        conn.close()
        return None, []
    c.execute("SELECT * FROM quiz_questions WHERE quiz_id = ?", (quiz_id,))
    questions = [dict(r) for r in c.fetchall()]
    conn.close()
    return dict(quiz), questions


def submit_quiz(quiz_id, answers, time_taken=0):
    """Score a quiz attempt. answers = {question_id: selected_letter}"""
    quiz, questions = get_quiz(quiz_id)
    if not quiz:
        return None

    score = 0
    total = len(questions)
    wrong_topics = []
    details = []

    for q in questions:
        qid = str(q['id'])
        selected = answers.get(qid, '')
        correct = q['correct_answer']
        is_correct = selected.upper() == correct.upper()
        if is_correct:
            score += 1
        else:
            wrong_topics.append(quiz.get('topic', 'General'))
        details.append({
            'question_id': q['id'],
            'selected': selected,
            'correct': correct,
            'is_correct': is_correct
        })

    percentage = round((score / total * 100), 1) if total > 0 else 0

    conn = _get_conn()
    c = conn.cursor()
    c.execute('''INSERT INTO quiz_attempts 
        (quiz_id, score, total, percentage, time_taken, answers, weak_topics)
        VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (quiz_id, score, total, percentage, time_taken,
         json.dumps(details), json.dumps(wrong_topics)))
    attempt_id = c.lastrowid
    conn.commit()
    conn.close()

    # Update topic mastery
    if quiz.get('topic') and quiz.get('subject'):
        _update_mastery(quiz['subject'], quiz['topic'], percentage)

    return attempt_id


def get_quiz_result(attempt_id):
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM quiz_attempts WHERE id = ?", (attempt_id,))
    attempt = c.fetchone()
    if not attempt:
        conn.close()
        return None, None, []
    attempt = dict(attempt)
    c.execute("SELECT * FROM quizzes WHERE id = ?", (attempt['quiz_id'],))
    quiz = dict(c.fetchone())
    c.execute("SELECT * FROM quiz_questions WHERE quiz_id = ?", (attempt['quiz_id'],))
    questions = [dict(r) for r in c.fetchall()]
    conn.close()
    attempt['answers'] = json.loads(attempt['answers']) if attempt['answers'] else []
    return attempt, quiz, questions


def get_quiz_history():
    conn = _get_conn()
    c = conn.cursor()
    c.execute("""SELECT qa.*, q.topic, q.subject, q.difficulty 
        FROM quiz_attempts qa JOIN quizzes q ON qa.quiz_id = q.id
        ORDER BY qa.attempted_at DESC LIMIT 20""")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


# ─── Study Plans ──────────────────────────────────────────────────────

def generate_study_plan(client, model, subject, topics, exam_date, hours_per_day=2):
    """Generate a study plan using AI."""
    today = datetime.now().strftime('%Y-%m-%d')
    prompt = f"""Create a detailed study plan for the subject "{subject}".

Topics to cover: {topics}
Today's date: {today}
Exam date: {exam_date}
Available study hours per day: {hours_per_day}

Return a JSON object with:
- "summary": brief overview of the plan (2-3 sentences)
- "total_days": number of days until exam
- "daily_plan": array of objects with:
  - "day": day number (1, 2, 3...)
  - "date": the date (YYYY-MM-DD)
  - "topics": array of topics to study
  - "activities": what to do (read, practice, quiz, revision)
  - "hours": hours allocated
- "revision_days": array of day numbers dedicated to revision
- "tips": array of 5 study tips specific to this subject

Return ONLY the JSON object, no other text."""

    system = "You are an expert academic planner. Create realistic, effective study plans. Respond with ONLY a valid JSON object. Do not include any explanation, commentary, or thinking."

    for attempt in range(3):
        try:
            raw = _ai_call(client, model, system, prompt)
            return _parse_json_response(raw)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Study plan generation parse attempt {attempt + 1} failed: {e}")
            if attempt == 2:
                raise
            time.sleep(0.5)


def save_study_plan(subject, exam_date, hours_per_day, plan_data):
    conn = _get_conn()
    c = conn.cursor()
    c.execute('''INSERT INTO study_plans (subject, exam_date, hours_per_day, plan_data)
        VALUES (?, ?, ?, ?)''', (subject, exam_date, hours_per_day, json.dumps(plan_data)))
    plan_id = c.lastrowid
    conn.commit()
    conn.close()
    return plan_id


def get_study_plans():
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM study_plans ORDER BY created_at DESC")
    rows = []
    for r in c.fetchall():
        d = dict(r)
        d['plan_data'] = json.loads(d['plan_data']) if d['plan_data'] else {}
        rows.append(d)
    conn.close()
    return rows


def get_study_plan(plan_id):
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM study_plans WHERE id = ?", (plan_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d['plan_data'] = json.loads(d['plan_data']) if d['plan_data'] else {}
    return d


# ─── Progress Tracking ───────────────────────────────────────────────

def log_study_session(subject, topic, duration_minutes, activity_type):
    conn = _get_conn()
    c = conn.cursor()
    c.execute('''INSERT INTO study_sessions (subject, topic, duration_minutes, activity_type)
        VALUES (?, ?, ?, ?)''', (subject, topic, duration_minutes, activity_type))
    conn.commit()
    conn.close()
    if subject and topic:
        _update_mastery(subject, topic, None, studied=True)


def get_progress_data():
    conn = _get_conn()
    c = conn.cursor()

    # Total study time
    c.execute("SELECT COALESCE(SUM(duration_minutes), 0) FROM study_sessions")
    total_minutes = c.fetchone()[0]

    # Total quizzes & avg score
    c.execute("SELECT COUNT(*), COALESCE(AVG(percentage), 0) FROM quiz_attempts")
    row = c.fetchone()
    total_quizzes = row[0]
    avg_score = round(row[1], 1)

    # Flashcard stats
    c.execute("SELECT COUNT(*) FROM flashcards")
    total_flashcards = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM flashcards WHERE confidence >= 4")
    mastered_cards = c.fetchone()[0]

    # Topics mastered vs weak
    c.execute("SELECT COUNT(*) FROM topic_mastery WHERE mastery_level >= 70")
    strong_topics = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM topic_mastery WHERE is_weak = 1")
    weak_topics = c.fetchone()[0]

    # Study sessions by activity
    c.execute("SELECT activity_type, COUNT(*), SUM(duration_minutes) FROM study_sessions GROUP BY activity_type")
    activities = [dict(r) for r in c.fetchall()]

    # Daily study (last 7 days)
    c.execute("""SELECT DATE(started_at) as day, SUM(duration_minutes) as mins
        FROM study_sessions GROUP BY day ORDER BY day DESC LIMIT 7""")
    daily_study = [dict(r) for r in c.fetchall()]

    # Recent quiz scores
    c.execute("""SELECT qa.percentage, qa.attempted_at, q.topic 
        FROM quiz_attempts qa JOIN quizzes q ON qa.quiz_id = q.id
        ORDER BY qa.attempted_at DESC LIMIT 10""")
    recent_scores = [dict(r) for r in c.fetchall()]

    # Subject breakdown
    c.execute("""SELECT subject, COUNT(*) as sessions, SUM(duration_minutes) as mins
        FROM study_sessions WHERE subject IS NOT NULL
        GROUP BY subject ORDER BY mins DESC""")
    subject_breakdown = [dict(r) for r in c.fetchall()]

    conn.close()

    return {
        'total_study_minutes': total_minutes,
        'total_study_hours': round(total_minutes / 60, 1),
        'total_quizzes': total_quizzes,
        'avg_quiz_score': avg_score,
        'total_flashcards': total_flashcards,
        'mastered_cards': mastered_cards,
        'strong_topics': strong_topics,
        'weak_topics': weak_topics,
        'activities': activities,
        'daily_study': daily_study,
        'recent_scores': recent_scores,
        'subject_breakdown': subject_breakdown
    }


def _update_mastery(subject, topic, score=None, studied=False):
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM topic_mastery WHERE subject = ? AND topic = ?", (subject, topic))
    row = c.fetchone()

    if row:
        row = dict(row)
        scores = json.loads(row['quiz_scores']) if row['quiz_scores'] else []
        times = row['times_studied']
        if score is not None:
            scores.append(score)
        if studied:
            times += 1
        avg = sum(scores) / len(scores) if scores else 0
        is_weak = 1 if (len(scores) >= 2 and avg < 50) else 0
        c.execute("""UPDATE topic_mastery SET 
            mastery_level = ?, quiz_scores = ?, times_studied = ?,
            is_weak = ?, last_studied = ?, updated_at = ?
            WHERE id = ?""",
            (round(avg, 1), json.dumps(scores), times, is_weak,
             datetime.now().isoformat(), datetime.now().isoformat(), row['id']))
    else:
        scores = [score] if score is not None else []
        avg = score if score is not None else 0
        is_weak = 1 if (score is not None and score < 50) else 0
        c.execute("""INSERT INTO topic_mastery 
            (subject, topic, mastery_level, quiz_scores, times_studied, is_weak, last_studied, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (subject, topic, avg, json.dumps(scores), 1 if studied else 0,
             is_weak, datetime.now().isoformat(), datetime.now().isoformat()))

    conn.commit()
    conn.close()


def detect_weak_topics():
    conn = _get_conn()
    c = conn.cursor()
    c.execute("""SELECT subject, topic, mastery_level, quiz_scores, times_studied
        FROM topic_mastery WHERE is_weak = 1 ORDER BY mastery_level ASC""")
    weak = [dict(r) for r in c.fetchall()]
    for w in weak:
        w['quiz_scores'] = json.loads(w['quiz_scores']) if w['quiz_scores'] else []
    conn.close()
    return weak


def get_all_mastery():
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM topic_mastery ORDER BY mastery_level ASC")
    rows = []
    for r in c.fetchall():
        d = dict(r)
        d['quiz_scores'] = json.loads(d['quiz_scores']) if d['quiz_scores'] else []
        rows.append(d)
    conn.close()
    return rows


# ─── Notes ────────────────────────────────────────────────────────────

def convert_to_notes(client, model, lecture_text, subject, title):
    """Convert lecture text to structured notes using AI."""
    prompt = f"""Convert the following lecture content into well-structured study notes for the subject "{subject}".

Title: {title}

Requirements:
- Start with a brief summary (3-4 sentences)
- Use clear headers and subheaders  
- Use bullet points for key concepts
- Highlight important terms with **bold**
- Include a "Key Takeaways" section at the end
- Add a "Quick Review Questions" section with 3-5 questions

Lecture Content:
{lecture_text[:5000]}

Return the notes in clean markdown format."""

    raw = _ai_call(client, model,
        "You are an expert note-taker. Create clear, comprehensive study notes from lectures. Do not use thinking tags.",
        prompt)
    # Clean any residual thinking tags
    raw = re.sub(r'<think>[\s\S]*?</think>', '', raw).strip()
    return raw


def save_notes(subject, title, content, source_type='lecture'):
    conn = _get_conn()
    c = conn.cursor()
    c.execute('''INSERT INTO notes (subject, title, content, source_type)
        VALUES (?, ?, ?, ?)''', (subject, title, content, source_type))
    note_id = c.lastrowid
    conn.commit()
    conn.close()
    return note_id


def get_all_notes():
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT id, subject, title, source_type, created_at FROM notes ORDER BY created_at DESC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_note(note_id):
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM notes WHERE id = ?", (note_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


# ─── Topic Prediction ────────────────────────────────────────────────

def predict_topics(client, model, subject, syllabus_topics, past_exam_topics=None):
    """Predict important exam topics using AI."""
    past = f"\nTopics from past exams: {past_exam_topics}" if past_exam_topics else ""
    prompt = f"""Analyze the following syllabus for "{subject}" and predict which topics are most likely to appear in the upcoming exam.{past}

Syllabus topics: {syllabus_topics}

Return a JSON object with:
- "high_priority": array of objects with "topic" and "reason" (most likely to appear)
- "medium_priority": array of objects with "topic" and "reason"
- "low_priority": array of objects with "topic" and "reason" (least likely)
- "predicted_questions": array of 5 sample questions that might appear
- "preparation_tips": array of 5 specific tips for this exam

Return ONLY the JSON object, no other text."""

    system = "You are an expert exam analyst. Predict important topics based on syllabus patterns. Respond with ONLY a valid JSON object. Do not include any explanation, commentary, or thinking."

    for attempt in range(3):
        try:
            raw = _ai_call(client, model, system, prompt)
            return _parse_json_response(raw)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Topic prediction parse attempt {attempt + 1} failed: {e}")
            if attempt == 2:
                raise
            time.sleep(0.5)


def save_prediction(subject, prediction_data):
    conn = _get_conn()
    c = conn.cursor()
    c.execute('''INSERT INTO predictions (subject, prediction_data)
        VALUES (?, ?)''', (subject, json.dumps(prediction_data)))
    pred_id = c.lastrowid
    conn.commit()
    conn.close()
    return pred_id


def get_predictions():
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM predictions ORDER BY created_at DESC LIMIT 10")
    rows = []
    for r in c.fetchall():
        d = dict(r)
        d['prediction_data'] = json.loads(d['prediction_data']) if d['prediction_data'] else {}
        rows.append(d)
    conn.close()
    return rows


# ─── Dashboard ────────────────────────────────────────────────────────

def get_dashboard_data():
    conn = _get_conn()
    c = conn.cursor()

    # Quick stats
    c.execute("SELECT COUNT(*) FROM quizzes")
    total_quizzes = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM flashcards")
    total_flashcards = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM notes")
    total_notes = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM pdfs")
    total_pdfs = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(duration_minutes), 0) FROM study_sessions")
    total_study_mins = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM topic_mastery WHERE is_weak = 1")
    weak_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM study_plans WHERE status = 'active'")
    active_plans = c.fetchone()[0]

    # Recent activity
    c.execute("""SELECT 'quiz' as type, q.topic as title, qa.percentage as detail, qa.attempted_at as ts
        FROM quiz_attempts qa JOIN quizzes q ON qa.quiz_id = q.id
        UNION ALL
        SELECT 'flashcard' as type, topic as title, CAST(COUNT(*) AS TEXT) as detail, MAX(created_at) as ts
        FROM flashcards GROUP BY topic
        UNION ALL
        SELECT 'note' as type, title, source_type as detail, created_at as ts FROM notes
        ORDER BY ts DESC LIMIT 8""")
    recent_activity = [dict(r) for r in c.fetchall()]

    # Due flashcards
    now = datetime.now().isoformat()
    c.execute("SELECT COUNT(*) FROM flashcards WHERE next_review IS NULL OR next_review <= ?", (now,))
    due_flashcards = c.fetchone()[0]

    conn.close()

    return {
        'total_quizzes': total_quizzes,
        'total_flashcards': total_flashcards,
        'total_notes': total_notes,
        'total_pdfs': total_pdfs,
        'total_study_hours': round(total_study_mins / 60, 1),
        'weak_topics': weak_count,
        'active_plans': active_plans,
        'due_flashcards': due_flashcards,
        'recent_activity': recent_activity
    }

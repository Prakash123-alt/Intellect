"""AI Question Paper Generator.

Supports three generation modes:
1. Similar Model Paper
2. Practice Paper
3. Predicted Exam Paper

Uses an LLM (Groq) to extract questions, compute frequency/trend/semantic
importance, and generate new papers with confidence scores.
"""

import os
import re
import json
import sqlite3
import logging
from collections import Counter
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import render_template, request, flash, redirect, url_for, session, jsonify

from dotenv import load_dotenv
load_dotenv()

from groq import Groq
from exam_platform import extract_any_text, _ai_call, _parse_json_response, UPLOAD_DIR

logger = logging.getLogger('question_paper')

QP_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'question_paper.db')


def _get_conn():
    conn = sqlite3.connect(QP_DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_qp_db():
    os.makedirs(os.path.dirname(QP_DB), exist_ok=True)
    conn = _get_conn()
    c = conn.cursor()
    c.executescript('''
        CREATE TABLE IF NOT EXISTS previous_papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT DEFAULT 'default',
            name TEXT,
            year INTEGER,
            exam_type TEXT,
            filename TEXT,
            original_name TEXT,
            file_path TEXT,
            extracted_text TEXT,
            page_count INTEGER DEFAULT 0,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS extracted_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_id INTEGER,
            text TEXT,
            marks INTEGER,
            section TEXT,
            subject TEXT,
            topics TEXT,
            year INTEGER,
            FOREIGN KEY (paper_id) REFERENCES previous_papers(id)
        );

        CREATE TABLE IF NOT EXISTS topic_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT DEFAULT 'default',
            topic TEXT,
            frequency INTEGER DEFAULT 0,
            years TEXT,
            trend_score REAL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS prediction_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT DEFAULT 'default',
            concept TEXT,
            frequency_score REAL DEFAULT 0,
            trend_score REAL DEFAULT 0,
            semantic_score REAL DEFAULT 0,
            combined_score REAL DEFAULT 0,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS generated_exam_papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT DEFAULT 'default',
            mode TEXT,
            pattern TEXT,
            questions TEXT,
            answer_key TEXT,
            predictions TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    conn.commit()
    conn.close()


def _extract_questions_with_llm(client, model, text, year=None, subject='General'):
    """Use the LLM to pull out a list of questions from a paper."""
    system = (
        "You are an exam document parser. Return ONLY valid JSON. "
        "Do not include any explanation, markdown, or thinking."
    )
    prompt = f"""Extract the individual questions from the following exam paper text.
For each question, return:
- text: the full question text
- marks: the marks assigned (integer, default 1)
- section: the section label like "A", "B", "C" if present, or ""
- topics: a list of 1-3 topic names the question covers

Year: {year or 'Unknown'}
Subject: {subject}

Paper text:
{text[:12000]}

Return JSON in this exact format:
{{"questions": [{{"text": "...", "marks": 1, "section": "A", "topics": ["..."]}}]}}
"""
    try:
        raw = _ai_call(client, model, system, prompt)
        data = _parse_json_response(raw)
        return data.get('questions', [])
    except Exception as e:
        logger.error(f"Question extraction failed: {e}")
        return []


def _split_questions_naive(text):
    """Fallback: split on question-number patterns."""
    # Try to split by lines starting with numbers like 1., 2), Q1 etc.
    parts = re.split(r'\n(?=\s*\d+[\.\)]\s)', text)
    if len(parts) < 2:
        parts = re.split(r'\n(?=Q\s*\d+[\.\)])', text)
    questions = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        m = re.match(r'^\s*\d+\s*[\.\)]\s*(.*)', p, re.DOTALL)
        if m:
            questions.append(m.group(1).strip())
    return questions


def _year_from_name(name):
    m = re.search(r'(20\d{2})', name)
    return int(m.group(1)) if m else None


def save_previous_paper(client, model, user_id, name, file_storage, subject='General'):
    """Save an uploaded previous-year paper and extract its questions."""
    original_name = secure_filename(file_storage.filename)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    saved_name = f'qp_{timestamp}_{original_name}'
    file_path = os.path.join(UPLOAD_DIR, saved_name)
    file_storage.save(file_path)

    year = _year_from_name(name)
    exam_type = 'unknown'

    text, page_count = extract_any_text(file_path, original_name)

    conn = _get_conn()
    c = conn.cursor()
    c.execute('''
        INSERT INTO previous_papers
        (user_id, name, year, exam_type, filename, original_name, file_path, extracted_text, page_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, name, year, exam_type, saved_name, original_name, file_path, text, page_count))
    paper_id = c.lastrowid
    conn.commit()
    conn.close()

    questions = _extract_questions_with_llm(client, model, text, year=year, subject=subject)
    if not questions:
        naive = _split_questions_naive(text)
        questions = [{'text': q, 'marks': 1, 'section': '', 'topics': []} for q in naive]

    conn = _get_conn()
    c = conn.cursor()
    for q in questions:
        c.execute('''
            INSERT INTO extracted_questions
            (paper_id, text, marks, section, subject, topics, year)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (paper_id, q.get('text', '')[:2000], int(q.get('marks', 1) or 1),
              q.get('section', '')[:10], subject, json.dumps(q.get('topics', []), ensure_ascii=False), year))
    conn.commit()
    conn.close()
    return paper_id


def get_user_papers(user_id='default'):
    conn = _get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM previous_papers WHERE user_id = ? ORDER BY uploaded_at DESC', (user_id,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_user_extracted_questions(user_id='default'):
    conn = _get_conn()
    c = conn.cursor()
    c.execute('''
        SELECT eq.* FROM extracted_questions eq
        JOIN previous_papers pp ON eq.paper_id = pp.id
        WHERE pp.user_id = ?
    ''', (user_id,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def _prepare_question_text(questions):
    """Return a compact JSON-ish list of questions for prompts."""
    items = []
    for q in questions:
        items.append({
            'text': q['text'][:300],
            'marks': q.get('marks', 1),
            'year': q.get('year'),
            'topics': q.get('topics', [])
        })
    return json.dumps(items, ensure_ascii=False, indent=2)


def _compute_topic_frequency(questions):
    """Compute topic counts and trend from extracted questions."""
    topic_counter = Counter()
    topic_years = {}
    for q in questions:
        try:
            tops = json.loads(q.get('topics', '[]')) if isinstance(q.get('topics'), str) else q.get('topics', [])
        except Exception:
            tops = []
        year = q.get('year') or 0
        for t in tops:
            t = t.strip()
            if t:
                topic_counter[t] += 1
                if t not in topic_years:
                    topic_years[t] = set()
                if year:
                    topic_years[t].add(year)
    return topic_counter, topic_years


def _build_prediction_scores(client, model, user_id, questions, pattern=None):
    """Use the LLM to produce frequency/trend/semantic combined scores."""
    system = (
        "You are an exam prediction engine. Return ONLY valid JSON. "
        "Do not include explanations or markdown."
    )
    prompt = f"""You are given a list of questions extracted from previous-year exam papers.
Analyze them and produce a ranked list of concepts most likely to appear in the next exam.

For each concept, compute:
- frequency_score (0-100): how often the concept appears across all papers
- trend_score (0-100): whether the concept is appearing more over recent years
- semantic_score (0-100): how important the concept is even if worded differently
- combined_score (0-100): weighted combination of the three

Previous questions:
{_prepare_question_text(questions)}

Return JSON in this format:
{{"predictions": [{{"concept": "...", "frequency_score": 85, "trend_score": 78, "semantic_score": 92, "combined_score": 88}}]}}
"""
    try:
        raw = _ai_call(client, model, system, prompt)
        data = _parse_json_response(raw)
        predictions = data.get('predictions', [])
    except Exception as e:
        logger.error(f"Prediction scoring failed: {e}")
        predictions = []

    # Also compute simple frequency table as fallback / augmentation
    topic_counter, topic_years = _compute_topic_frequency(questions)
    if not predictions and topic_counter:
        for topic, count in topic_counter.most_common(50):
            years = sorted(topic_years.get(topic, []))
            trend = min(100, (len(years) * 20) + (count * 5))
            predictions.append({
                'concept': topic,
                'frequency_score': min(100, count * 10),
                'trend_score': trend,
                'semantic_score': 50,
                'combined_score': min(100, (min(100, count * 10) + trend + 50) / 3)
            })

    conn = _get_conn()
    c = conn.cursor()
    c.execute('DELETE FROM prediction_scores WHERE user_id = ?', (user_id,))
    c.execute('DELETE FROM topic_analysis WHERE user_id = ?', (user_id,))
    for p in predictions:
        c.execute('''
            INSERT INTO prediction_scores
            (user_id, concept, frequency_score, trend_score, semantic_score, combined_score, details)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, p.get('concept', '')[:250],
              p.get('frequency_score', 0), p.get('trend_score', 0),
              p.get('semantic_score', 0), p.get('combined_score', 0),
              json.dumps(p, ensure_ascii=False)))
    for topic, count in topic_counter.most_common(100):
        years = sorted(topic_years.get(topic, []))
        c.execute('''
            INSERT INTO topic_analysis (user_id, topic, frequency, years, trend_score)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, topic, count, json.dumps(years), min(100, len(years) * 20 + count * 5)))
    conn.commit()
    conn.close()
    return predictions


def get_prediction_scores(user_id='default'):
    conn = _get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM prediction_scores WHERE user_id = ? ORDER BY combined_score DESC', (user_id,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def _build_pattern_description(pattern_text, default_total=35):
    if not pattern_text:
        return f"Default pattern: total marks {default_total}"
    return pattern_text


def _common_system():
    return "You are an expert university exam paper generator. Return ONLY valid JSON. No markdown."


def _paper_prompt(mode, questions, pattern, predictions=None, syllabus_text=None):
    pattern_desc = _build_pattern_description(pattern)
    questions_json = _prepare_question_text(questions)
    pred_json = json.dumps(predictions[:30] if predictions else [], ensure_ascii=False, indent=2)
    extra = f"\nSyllabus / Notes:\n{syllabus_text[:5000]}" if syllabus_text else ""

    if mode == 'similar':
        system = _common_system()
        prompt = f"""Generate a "Similar Model Paper" that closely resembles the previous papers.
Use the same structure, difficulty, and question style. Match the pattern described below.

Pattern:
{pattern_desc}

Previous questions:
{questions_json}{extra}

Return JSON with this format:
{{"title": "...", "sections": [{{"name": "A", "questions": [{{"text": "...", "marks": 1, "confidence": 80}}]}}], "answer_key": [{{"question_index": 0, "answer": "..."}}]}}
"""
    elif mode == 'practice':
        system = _common_system()
        prompt = f"""Generate a "Practice Paper" that covers the entire syllabus with easy, medium, and hard questions.
Balance topics, avoid repetition, and use the pattern below.

Pattern:
{pattern_desc}

Previous questions:
{questions_json}{extra}

Return JSON with this format:
{{"title": "...", "sections": [{{"name": "A", "questions": [{{"text": "...", "marks": 1, "difficulty": "easy", "confidence": 75}}]}}], "answer_key": [{{"question_index": 0, "answer": "..."}}]}}
"""
    else:  # predicted
        system = _common_system()
        prompt = f"""Generate a "Predicted Exam Paper" using the prediction scores.
Focus on the highest ranked concepts and produce the most likely questions for the next exam.

Pattern:
{pattern_desc}

Previous questions:
{questions_json}

Prediction scores:
{pred_json}{extra}

Return JSON with this format:
{{"title": "...", "sections": [{{"name": "A", "questions": [{{"text": "...", "marks": 1, "confidence": 95, "predicted_concept": "..."}}]}}], "answer_key": [{{"question_index": 0, "answer": "..."}}]}}
"""
    return system, prompt


def generate_paper(client, model, user_id, mode, pattern=None, syllabus_text=None):
    """Generate a paper in one of the three modes."""
    questions = get_user_extracted_questions(user_id)
    if not questions:
        raise ValueError("No previous papers or extracted questions available. Upload papers first.")

    predictions = None
    if mode == 'predicted':
        predictions = _build_prediction_scores(client, model, user_id, questions, pattern)

    system, prompt = _paper_prompt(mode, questions, pattern, predictions, syllabus_text)
    try:
        raw = _ai_call(client, model, system, prompt)
        data = _parse_json_response(raw)
    except Exception as e:
        logger.error(f"Paper generation failed for mode {mode}: {e}")
        raise

    conn = _get_conn()
    c = conn.cursor()
    c.execute('''
        INSERT INTO generated_exam_papers (user_id, mode, pattern, questions, answer_key, predictions)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, mode, pattern or '',
          json.dumps(data.get('sections', []), ensure_ascii=False),
          json.dumps(data.get('answer_key', []), ensure_ascii=False),
          json.dumps(predictions or [], ensure_ascii=False)))
    paper_id = c.lastrowid
    conn.commit()
    conn.close()
    return paper_id, data


def get_generated_paper(paper_id, user_id='default'):
    conn = _get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM generated_exam_papers WHERE id = ? AND user_id = ?', (paper_id, user_id))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    row = dict(row)
    for k in ('questions', 'answer_key', 'predictions'):
        try:
            row[k] = json.loads(row[k] or '[]')
        except Exception:
            row[k] = []
    return row


def get_user_generated_papers(user_id='default'):
    conn = _get_conn()
    c = conn.cursor()
    c.execute('SELECT id, mode, pattern, created_at FROM generated_exam_papers WHERE user_id = ? ORDER BY created_at DESC', (user_id,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def _save_resource_file(file_storage):
    original_name = secure_filename(file_storage.filename)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    saved_name = f'res_{timestamp}_{original_name}'
    file_path = os.path.join(UPLOAD_DIR, saved_name)
    file_storage.save(file_path)
    text, _ = extract_any_text(file_path, original_name)
    return original_name, file_path, text


def register_question_paper_routes(app, client, model):
    """Register all question-paper routes on the Flask app."""
    init_qp_db()

    @app.route('/question-paper')
    def question_paper_dashboard():
        user_id = session.get('user_id', 'default')
        papers = get_user_papers(user_id)
        generated = get_user_generated_papers(user_id)
        predictions = get_prediction_scores(user_id)
        pattern = session.get('qp_pattern', '')
        return render_template('question_paper.html',
                               papers=papers,
                               generated=generated,
                               predictions=predictions,
                               pattern=pattern,
                               active_page='question_paper')

    @app.route('/question-paper/upload', methods=['POST'])
    def question_paper_upload():
        user_id = session.get('user_id', 'default')
        subject = request.form.get('subject', 'General').strip()
        pattern = request.form.get('pattern', '').strip()
        if pattern:
            session['qp_pattern'] = pattern

        if 'papers' not in request.files:
            flash('No previous-year paper uploaded.', 'error')
            return redirect(url_for('question_paper_dashboard'))

        files = request.files.getlist('papers')
        names = request.form.getlist('paper_name')
        if not names:
            names = [f.filename for f in files]

        for f, name in zip(files, names):
            if not f or not f.filename:
                continue
            ext = f.filename.rsplit('.', 1)[-1].lower()
            if ext not in ('pdf', 'docx', 'txt'):
                flash(f'Skipped {f.filename}: only PDF, DOCX and TXT are allowed.', 'warning')
                continue
            save_previous_paper(client, model, user_id, name or f.filename, f, subject=subject)

        flash('Previous-year paper(s) uploaded and analyzed.', 'success')
        return redirect(url_for('question_paper_dashboard'))

    @app.route('/question-paper/resources', methods=['POST'])
    def question_paper_resources():
        user_id = session.get('user_id', 'default')
        if 'resources' not in request.files:
            flash('No resource files uploaded.', 'error')
            return redirect(url_for('question_paper_dashboard'))
        files = request.files.getlist('resources')
        combined = []
        for f in files:
            if not f or not f.filename:
                continue
            _, _, text = _save_resource_file(f)
            combined.append(text)
        session['qp_resources'] = '\n---\n'.join(combined)
        flash('Resources uploaded.', 'success')
        return redirect(url_for('question_paper_dashboard'))

    @app.route('/question-paper/analyze', methods=['POST'])
    def question_paper_analyze():
        user_id = session.get('user_id', 'default')
        questions = get_user_extracted_questions(user_id)
        if not questions:
            flash('Upload previous papers first.', 'error')
            return redirect(url_for('question_paper_dashboard'))
        _build_prediction_scores(client, model, user_id, questions)
        flash('Prediction analysis complete.', 'success')
        return redirect(url_for('question_paper_dashboard'))

    @app.route('/question-paper/generate', methods=['POST'])
    def question_paper_generate():
        user_id = session.get('user_id', 'default')
        mode = request.form.get('mode', 'similar')
        pattern = request.form.get('pattern', '').strip()
        if pattern:
            session['qp_pattern'] = pattern
        syllabus_text = session.get('qp_resources', '')
        try:
            paper_id, _ = generate_paper(client, model, user_id, mode, pattern=pattern, syllabus_text=syllabus_text)
            return redirect(url_for('question_paper_result', paper_id=paper_id))
        except Exception as e:
            logger.error(f"Generate {mode} failed: {e}")
            flash(str(e), 'error')
            return redirect(url_for('question_paper_dashboard'))

    @app.route('/question-paper/result/<int:paper_id>')
    def question_paper_result(paper_id):
        user_id = session.get('user_id', 'default')
        paper = get_generated_paper(paper_id, user_id)
        if not paper:
            flash('Generated paper not found.', 'error')
            return redirect(url_for('question_paper_dashboard'))
        return render_template('generated_paper.html', paper=paper, active_page='question_paper')

    @app.route('/question-paper/api/predictions')
    def question_paper_api_predictions():
        user_id = session.get('user_id', 'default')
        return jsonify(get_prediction_scores(user_id))

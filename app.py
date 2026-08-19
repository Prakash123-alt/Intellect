from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash
from groq import Groq
import os
import re
import time
import json
import markdown
from datetime import datetime
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

from pipeline import (store_qa, preprocess_text, get_analytics,
                      export_training_data, log_stream_event,
                      process_pending_events, get_stream_stats, init_db)
from exam_platform import (
    init_exam_db, extract_pdf_text, save_pdf, get_pdfs, get_pdf,
    generate_flashcards, save_flashcards, get_flashcards, get_due_flashcards,
    update_flashcard_review, get_flashcard_stats,
    generate_quiz, save_quiz, get_all_quizzes, get_quiz, submit_quiz,
    get_quiz_result, get_quiz_history,
    generate_study_plan, save_study_plan, get_study_plans, get_study_plan,
    log_study_session, get_progress_data, detect_weak_topics, get_all_mastery,
    convert_to_notes, save_notes, get_all_notes, get_note,
    predict_topics, save_prediction, get_predictions,
    get_dashboard_data, UPLOAD_DIR
)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "intellect-ai-exam-prep-2026")
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max upload

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = "openai/gpt-oss-20b"
SYSTEM_PROMPT = "You are a helpful assistant. Give clear, concise answers. Do not include any thinking or reasoning tags."

# Initialize databases
init_db()
init_exam_db()


# ─── Context Injection ───────────────────────────────────────────────

@app.context_processor
def inject_globals():
    """Inject common data into all templates."""
    stats = get_flashcard_stats()
    weak = detect_weak_topics()
    return {
        'due_flashcards': stats.get('due', 0),
        'weak_count': len(weak)
    }


# ─── Helper ──────────────────────────────────────────────────────────

def ask_groq(question, context=None):
    start = time.time()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if context:
        messages.append({"role": "system", "content": f"Use this context to answer:\n{context[:4000]}"})
    messages.append({"role": "user", "content": question})
    response = client.chat.completions.create(model=MODEL, messages=messages)
    elapsed = time.time() - start
    raw = response.choices[0].message.content
    raw = preprocess_text(raw)
    tokens = response.usage.total_tokens if response.usage else 0
    store_qa(question, raw, MODEL, elapsed, tokens)
    log_stream_event('web', 'query', {'question': question, 'response_time': elapsed})
    return raw, elapsed


# ─── Dashboard ────────────────────────────────────────────────────────

@app.route('/')
def dashboard():
    data = get_dashboard_data()
    return render_template('dashboard.html', data=data, active_page='dashboard')


# ─── Ask AI (Q&A) ────────────────────────────────────────────────────

@app.route('/ask', methods=['GET', 'POST'])
def ask():
    answer = ""
    question = ""
    elapsed = 0
    if request.method == 'POST':
        question = request.form.get('question', '')
        if question.strip():
            raw, elapsed = ask_groq(question)
            answer = markdown.markdown(raw, extensions=['tables', 'fenced_code'])
            log_study_session('General', 'Q&A', 2, 'reading')
    return render_template('ask.html', answer=answer, question=question,
                         elapsed=round(elapsed, 2), active_page='ask')


# ─── API endpoint (existing, for Flutter) ────────────────────────────

@app.route('/api/ask', methods=['POST'])
def api_ask():
    data = request.get_json()
    question = data.get('question', '')
    if not question.strip():
        return jsonify({'error': 'Empty question'}), 400
    log_stream_event('flutter', 'query', {'question': question})
    raw, elapsed = ask_groq(question)
    return jsonify({'answer': raw, 'response_time': elapsed})


# ─── PDF Study ────────────────────────────────────────────────────────

@app.route('/pdf', methods=['GET'])
def pdf_study():
    pdfs = get_pdfs()
    return render_template('pdf_study.html', pdfs=pdfs, active_page='pdf')


@app.route('/pdf/upload', methods=['POST'])
def pdf_upload():
    if 'pdf_file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('pdf_study'))
    file = request.files['pdf_file']
    if file.filename == '' or not file.filename.lower().endswith('.pdf'):
        flash('Please upload a valid PDF file', 'error')
        return redirect(url_for('pdf_study'))

    subject = request.form.get('subject', 'General')
    filename = secure_filename(file.filename)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    saved_name = f"{timestamp}_{filename}"
    filepath = os.path.join(UPLOAD_DIR, saved_name)
    file.save(filepath)

    text, page_count = extract_pdf_text(filepath)
    if not text.strip():
        flash('Could not extract text from PDF. The file may be scanned/image-based.', 'error')
        return redirect(url_for('pdf_study'))

    save_pdf(subject, saved_name, filename, text, page_count)
    flash(f'PDF uploaded: {filename} ({page_count} pages)', 'success')
    return redirect(url_for('pdf_study'))


@app.route('/pdf/ask', methods=['POST'])
def pdf_ask():
    pdf_id = request.form.get('pdf_id')
    question = request.form.get('question', '')
    pdf = get_pdf(int(pdf_id)) if pdf_id else None
    if not pdf or not question.strip():
        flash('Select a PDF and enter a question', 'error')
        return redirect(url_for('pdf_study'))

    raw, elapsed = ask_groq(question, context=pdf['extracted_text'])
    answer = markdown.markdown(raw, extensions=['tables', 'fenced_code'])
    pdfs = get_pdfs()
    log_study_session(pdf.get('subject', 'General'), 'PDF Study', 3, 'reading')
    return render_template('pdf_study.html', pdfs=pdfs, answer=answer,
                         question=question, selected_pdf=pdf_id,
                         elapsed=round(elapsed, 2), active_page='pdf')


# ─── Flashcards ───────────────────────────────────────────────────────

@app.route('/flashcards', methods=['GET'])
def flashcards_page():
    cards = get_flashcards()
    due = get_due_flashcards()
    stats = get_flashcard_stats()
    return render_template('flashcards.html', cards=cards, due_cards=due,
                         stats=stats, active_page='flashcards')


@app.route('/flashcards/generate', methods=['POST'])
def flashcards_generate():
    topic = request.form.get('topic', '')
    subject = request.form.get('subject', 'General')
    count = int(request.form.get('count', 10))
    context = request.form.get('context', '')

    if not topic.strip():
        flash('Please enter a topic', 'error')
        return redirect(url_for('flashcards_page'))

    try:
        cards = generate_flashcards(client, MODEL, topic, count, context if context.strip() else None)
        saved = save_flashcards(subject, topic, cards)
        log_study_session(subject, topic, 5, 'flashcard')
        flash(f'Generated {saved} flashcards on "{topic}"', 'success')
    except Exception as e:
        flash(f'Error generating flashcards: {str(e)}', 'error')
    return redirect(url_for('flashcards_page'))


@app.route('/flashcards/review', methods=['POST'])
def flashcards_review():
    card_id = request.form.get('card_id')
    confidence = int(request.form.get('confidence', 3))
    if card_id:
        update_flashcard_review(int(card_id), confidence)
    return jsonify({'status': 'ok'})


# ─── Quiz ─────────────────────────────────────────────────────────────

@app.route('/quiz', methods=['GET'])
def quiz_page():
    quizzes = get_all_quizzes()
    history = get_quiz_history()
    return render_template('quiz.html', quizzes=quizzes, history=history, active_page='quiz')


@app.route('/quiz/generate', methods=['POST'])
def quiz_generate():
    topic = request.form.get('topic', '')
    subject = request.form.get('subject', 'General')
    difficulty = request.form.get('difficulty', 'medium')
    count = int(request.form.get('count', 10))
    context = request.form.get('context', '')

    if not topic.strip():
        flash('Please enter a topic', 'error')
        return redirect(url_for('quiz_page'))

    try:
        questions = generate_quiz(client, MODEL, topic, difficulty, count,
                                  context if context.strip() else None)
        quiz_id = save_quiz(subject, topic, difficulty, questions)
        flash(f'Quiz created with {len(questions)} questions on "{topic}"', 'success')
        return redirect(url_for('quiz_take', quiz_id=quiz_id))
    except Exception as e:
        flash(f'Error generating quiz: {str(e)}', 'error')
        return redirect(url_for('quiz_page'))


@app.route('/quiz/take/<int:quiz_id>')
def quiz_take(quiz_id):
    quiz, questions = get_quiz(quiz_id)
    if not quiz:
        flash('Quiz not found', 'error')
        return redirect(url_for('quiz_page'))
    return render_template('quiz_take.html', quiz=quiz, questions=questions, active_page='quiz')


@app.route('/quiz/submit/<int:quiz_id>', methods=['POST'])
def quiz_submit(quiz_id):
    answers = {}
    for key, value in request.form.items():
        if key.startswith('q_'):
            qid = key[2:]
            answers[qid] = value
    time_taken = float(request.form.get('time_taken', 0))
    attempt_id = submit_quiz(quiz_id, answers, time_taken)
    if attempt_id:
        quiz, _ = get_quiz(quiz_id)
        log_study_session(quiz.get('subject', 'General'), quiz.get('topic', ''), 10, 'quiz')
        return redirect(url_for('quiz_result_page', attempt_id=attempt_id))
    flash('Error submitting quiz', 'error')
    return redirect(url_for('quiz_page'))


@app.route('/quiz/result/<int:attempt_id>')
def quiz_result_page(attempt_id):
    attempt, quiz, questions = get_quiz_result(attempt_id)
    if not attempt:
        flash('Result not found', 'error')
        return redirect(url_for('quiz_page'))
    return render_template('quiz_result.html', attempt=attempt, quiz=quiz,
                         questions=questions, active_page='quiz')


# ─── Study Plan ───────────────────────────────────────────────────────

@app.route('/study-plan', methods=['GET'])
def study_plan_page():
    plans = get_study_plans()
    return render_template('study_plan.html', plans=plans, active_page='study_plan')


@app.route('/study-plan/create', methods=['POST'])
def study_plan_create():
    subject = request.form.get('subject', '')
    topics = request.form.get('topics', '')
    exam_date = request.form.get('exam_date', '')
    hours = float(request.form.get('hours_per_day', 2))

    if not subject.strip() or not topics.strip() or not exam_date:
        flash('Please fill in all fields', 'error')
        return redirect(url_for('study_plan_page'))

    try:
        plan = generate_study_plan(client, MODEL, subject, topics, exam_date, hours)
        save_study_plan(subject, exam_date, hours, plan)
        flash(f'Study plan created for "{subject}"', 'success')
    except Exception as e:
        flash(f'Error creating study plan: {str(e)}', 'error')
    return redirect(url_for('study_plan_page'))


@app.route('/study-plan/<int:plan_id>')
def study_plan_detail(plan_id):
    plan = get_study_plan(plan_id)
    if not plan:
        flash('Plan not found', 'error')
        return redirect(url_for('study_plan_page'))
    return render_template('study_plan.html', plans=get_study_plans(),
                         selected_plan=plan, active_page='study_plan')


# ─── Progress ─────────────────────────────────────────────────────────

@app.route('/progress')
def progress_page():
    data = get_progress_data()
    weak = detect_weak_topics()
    mastery = get_all_mastery()
    return render_template('progress.html', data=data, weak_topics=weak,
                         mastery=mastery, active_page='progress')


@app.route('/progress/session', methods=['POST'])
def progress_log_session():
    subject = request.form.get('subject', '')
    topic = request.form.get('topic', '')
    duration = int(request.form.get('duration', 0))
    activity = request.form.get('activity_type', 'reading')
    if subject and duration > 0:
        log_study_session(subject, topic, duration, activity)
        flash('Study session logged', 'success')
    else:
        flash('Please fill in subject and duration', 'error')
    return redirect(url_for('progress_page'))


# ─── Notes ────────────────────────────────────────────────────────────

@app.route('/notes', methods=['GET'])
def notes_page():
    notes = get_all_notes()
    note_id = request.args.get('view')
    selected_note = get_note(int(note_id)) if note_id else None
    if selected_note:
        selected_note['content_html'] = markdown.markdown(
            selected_note['content'], extensions=['tables', 'fenced_code'])
    return render_template('notes.html', notes=notes, selected_note=selected_note,
                         active_page='notes')


@app.route('/notes/convert', methods=['POST'])
def notes_convert():
    lecture_text = request.form.get('lecture_text', '')
    subject = request.form.get('subject', 'General')
    title = request.form.get('title', 'Untitled Notes')

    if not lecture_text.strip():
        flash('Please enter lecture content', 'error')
        return redirect(url_for('notes_page'))

    try:
        notes_content = convert_to_notes(client, MODEL, lecture_text, subject, title)
        note_id = save_notes(subject, title, notes_content, 'lecture')
        log_study_session(subject, title, 5, 'notes')
        flash(f'Notes created: "{title}"', 'success')
        return redirect(url_for('notes_page', view=note_id))
    except Exception as e:
        flash(f'Error converting notes: {str(e)}', 'error')
        return redirect(url_for('notes_page'))


# ─── Predict Topics ──────────────────────────────────────────────────

@app.route('/predict', methods=['GET'])
def predict_page():
    predictions = get_predictions()
    return render_template('predict.html', predictions=predictions, active_page='predict')


@app.route('/predict/analyze', methods=['POST'])
def predict_analyze():
    subject = request.form.get('subject', '')
    syllabus = request.form.get('syllabus_topics', '')
    past = request.form.get('past_exam_topics', '')

    if not subject.strip() or not syllabus.strip():
        flash('Please enter subject and syllabus topics', 'error')
        return redirect(url_for('predict_page'))

    try:
        prediction = predict_topics(client, MODEL, subject, syllabus,
                                    past if past.strip() else None)
        save_prediction(subject, prediction)
        flash(f'Topic predictions generated for "{subject}"', 'success')
    except Exception as e:
        flash(f'Error predicting topics: {str(e)}', 'error')
    return redirect(url_for('predict_page'))


# ─── Analytics (existing, preserved) ─────────────────────────────────

@app.route('/analytics')
def analytics():
    data = get_analytics()
    stream = get_stream_stats()
    return render_template('analytics.html', analytics=data, stream=stream, active_page='analytics')


# ─── Export (existing) ────────────────────────────────────────────────

@app.route('/export/<fmt>')
def export(fmt):
    if fmt not in ('json', 'csv'):
        return "Invalid format", 400
    filepath, count = export_training_data(format=fmt)
    return send_file(filepath, as_attachment=True)


@app.route('/process-events')
def process_events():
    count = process_pending_events()
    return jsonify({'processed': count})


if __name__ == '__main__':
    app.run(debug=True)

from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash
from groq import Groq
import os
import re
import time
import json
import markdown
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

from pipeline import (store_qa, preprocess_text, get_analytics,
                      export_training_data, log_stream_event,
                      process_pending_events, get_stream_stats, init_db)
from exam_platform import (
    init_exam_db, extract_pdf_text, save_pdf, get_pdfs, get_pdf, get_pdf_text_range,
    analyze_pdf_difficulty, save_pdf_difficulty_analysis,
    generate_flashcards, save_flashcards, get_flashcards, get_due_flashcards,
    update_flashcard_review, get_flashcard_stats,
    generate_quiz, generate_exam_quiz, save_quiz, get_all_quizzes, get_quiz, submit_quiz,
    get_quiz_result, get_quiz_history,
    get_study_plans, get_study_plan, create_smart_study_plan, update_task_status,
    rebalance_plan, get_plan_summary_stats, get_study_materials, get_dashboard_study_overview,
    group_tasks_for_display,
    log_study_session, get_progress_data, detect_weak_topics, get_all_mastery,
    convert_to_notes, save_notes, get_all_notes, get_note,
    save_exam_document, get_exam_documents, extract_any_text,
    save_knowledge_document, get_knowledge_documents,
    analyze_exam_documents, save_full_prediction, get_predictions, get_prediction,
    generate_practice_test, export_prediction, export_quiz,
    get_dashboard_data, _ai_call, UPLOAD_DIR
)
from rag import query_knowledge
from media_notes import (
    process_media_upload, get_all_media_notes, get_media_note
)
from youtube_notes import (
    process_youtube_url, get_all_youtube_notes, get_youtube_note,
    _format_duration
)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "intellect-ai-exam-prep-2026")
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB max upload

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
    study_overview = get_dashboard_study_overview()
    return render_template('dashboard.html', data=data, study_overview=study_overview, active_page='dashboard')


# ─── Ask AI (Q&A) ────────────────────────────────────────────────────

@app.route('/ask', methods=['GET', 'POST'])
def ask():
    answer = ""
    raw = ""
    question = ""
    subject = request.args.get('subject', '')
    elapsed = 0
    if request.method == 'POST':
        question = request.form.get('question', '')
        subject = request.form.get('subject', '')
        use_rag = request.form.get('use_rag') == 'on'
        if question.strip():
            if use_rag and subject.strip():
                chunks = query_knowledge(subject.strip(), question, top_k=5)
                if chunks:
                    context = '\n\n---\n\n'.join(chunks)
                    prompt = f"""Answer the question based only on the provided context.

Context:
{context[:4000]}

Question: {question}

If the answer is not in the context, say: I cannot find the answer in the provided documents."""
                    raw, elapsed = ask_groq(prompt)
                else:
                    raw, elapsed = ask_groq(question, context='No relevant passages found in the knowledge base for this subject.')
            else:
                raw, elapsed = ask_groq(question)
            answer = markdown.markdown(raw, extensions=['tables', 'fenced_code'])
            log_study_session(subject or 'General', 'Q&A', 2, 'reading')
    documents = get_knowledge_documents(subject if subject else None)
    return render_template('ask.html', answer=answer, raw=raw, question=question, subject=subject,
                         documents=documents, elapsed=round(elapsed, 2), active_page='ask')


ALLOWED_KB_EXTS = ('.pdf', '.docx', '.pptx', '.txt')


@app.route('/knowledge/upload', methods=['POST'])
def knowledge_upload():
    if 'kb_file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('ask'))

    file = request.files['kb_file']
    if file.filename == '' or not file.filename.lower().endswith(ALLOWED_KB_EXTS):
        flash('Please upload a PDF, DOCX, PPTX, or TXT file', 'error')
        return redirect(url_for('ask'))

    subject = request.form.get('subject', '').strip()
    if not subject:
        flash('Please enter a subject for this knowledge base', 'error')
        return redirect(url_for('ask'))

    filename = secure_filename(file.filename)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    saved_name = f"{timestamp}_{filename}"
    filepath = os.path.join(UPLOAD_DIR, saved_name)
    file.save(filepath)

    text, _ = extract_any_text(filepath, filename)
    if not text.strip():
        flash('Could not extract text from the file. The file may be empty or image-based.', 'error')
        return redirect(url_for('ask'))

    try:
        doc_id = save_knowledge_document(subject, filename.rsplit('.', 1)[-1].lower(), saved_name, filename, text)
        flash(f'Indexed {filename} ({subject}) into the RAG knowledge base', 'success')
        return redirect(url_for('ask', subject=subject))
    except Exception as e:
        app.logger.error(f'RAG upload failed: {e}', exc_info=True)
        flash(f'RAG upload failed: {str(e)}', 'error')
        return redirect(url_for('ask'))


# ─── Visual Learning Generator ────────────────────────────────────────

DIAGRAM_TYPES = ('mindmap', 'flowchart', 'concept', 'process')


@app.route('/visualize', methods=['GET', 'POST'])
def visualize():
    content = request.form.get('content', '') or request.args.get('content', '')
    diagram_type = request.form.get('diagram_type', 'mindmap') or request.args.get('diagram_type', 'mindmap')
    if diagram_type not in DIAGRAM_TYPES:
        diagram_type = 'mindmap'
    mermaid_code = ''
    if request.method == 'POST' and content.strip():
        try:
            prompt = f"""Convert the following explanation into a {diagram_type} using valid Mermaid syntax.
Write ONLY the Mermaid code. Do not include any explanation, markdown code fences, or thinking tags.
Use one node per line with 2-space indentation for child nodes.

Diagram rules:
- mindmap: start with "mindmap" on its own line, then use "root((Topic))" and indented sub-items.
- flowchart: use "flowchart TD" and use arrows like "A[Start] --> B[Next]".
- concept: use "graph TD" with node names and "-->" links.
- process: use "flowchart LR" with steps linked by arrows.

Explanation:
{content[:4000]}"""
            raw = _ai_call(client, MODEL,
                'You are an expert at generating valid Mermaid diagrams. Return only the Mermaid code, no explanation.',
                prompt)
            # Strip thinking tags, code fences and any leading 'mermaid' label
            raw = re.sub(r'\s*<\|/?think\|>\s*', '', raw)
            raw = re.sub(r' thinking[\s\S]*? clicking', '', raw)
            mermaid_code = re.sub(r'```(?:mermaid)?\s*|```', '', raw, flags=re.IGNORECASE).strip()
            mermaid_code = re.sub(r'^\s*mermaid\s*\n', '', mermaid_code, flags=re.IGNORECASE)
        except Exception as e:
            app.logger.error(f'Visualize generation failed: {e}', exc_info=True)
            flash(f'Could not generate diagram: {str(e)}', 'error')
    return render_template('visualize.html', content=content, diagram_type=diagram_type,
                         mermaid_code=mermaid_code, active_page='visualize')

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

def _prep_pdfs_for_template(pdfs):
    """Parse the JSON difficulty_analysis column into a list for template rendering."""
    for pdf in pdfs:
        raw = pdf.get('difficulty_analysis')
        pdf['difficulty_analysis'] = json.loads(raw) if raw else None
    return pdfs


@app.route('/pdf', methods=['GET'])
def pdf_study():
    pdfs = _prep_pdfs_for_template(get_pdfs())
    expand = request.args.get('expand', type=int)
    return render_template('pdf_study.html', pdfs=pdfs, expand_pdf=expand, active_page='pdf')


@app.route('/pdf/analyze-difficulty', methods=['POST'])
def pdf_analyze_difficulty():
    pdf_id = request.form.get('pdf_id', type=int)
    pdf = get_pdf(pdf_id) if pdf_id else None
    if not pdf:
        flash('PDF not found', 'error')
        return redirect(url_for('pdf_study'))

    try:
        analysis = analyze_pdf_difficulty(client, MODEL, pdf.get('subject', 'General'), pdf['extracted_text'])
        save_pdf_difficulty_analysis(pdf_id, analysis)
        flash(f'Found {len(analysis)} difficult concept(s) in "{pdf["original_name"]}"', 'success')
    except Exception as e:
        flash(f'Error analyzing difficult concepts: {str(e)}', 'error')
    return redirect(url_for('pdf_study', expand=pdf_id) + f'#pdf-{pdf_id}')


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

    text, page_count, page_texts = extract_pdf_text(filepath)
    if not text.strip():
        flash('Could not extract text from PDF. The file may be scanned/image-based.', 'error')
        return redirect(url_for('pdf_study'))

    save_pdf(subject, saved_name, filename, text, page_count, page_texts)
    flash(f'PDF uploaded: {filename} ({page_count} pages)', 'success')
    return redirect(url_for('pdf_study'))


def _save_uploaded_pdf(file, subject):
    """Save an uploaded PDF file, extract its text, and store it. Returns the pdf dict."""
    filename = secure_filename(file.filename)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    saved_name = f"{timestamp}_{filename}"
    filepath = os.path.join(UPLOAD_DIR, saved_name)
    file.save(filepath)

    text, page_count, page_texts = extract_pdf_text(filepath)
    if not text.strip():
        return None
    pdf_id = save_pdf(subject, saved_name, filename, text, page_count, page_texts)
    return get_pdf(pdf_id)


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
    pdfs = _prep_pdfs_for_template(get_pdfs())
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
    pdfs = get_pdfs()
    return render_template('quiz.html', quizzes=quizzes, history=history, pdfs=pdfs, active_page='quiz')


@app.route('/quiz/generate', methods=['POST'])
def quiz_generate():
    topic = request.form.get('topic', '')
    subject = request.form.get('subject', 'General')
    difficulty = request.form.get('difficulty', 'medium')
    question_type = request.form.get('question_type', 'mcq')
    count = int(request.form.get('count', 10))
    context = request.form.get('context', '')
    source_mode = request.form.get('source_mode', 'topic')  # 'topic' or 'pdf'

    context_text = context.strip() or None
    source_pdf_id = None
    page_range = None

    if source_mode == 'pdf':
        pdf = None
        upload = request.files.get('pdf_file')
        if upload and upload.filename:
            if not upload.filename.lower().endswith('.pdf'):
                flash('Please upload a valid PDF file', 'error')
                return redirect(url_for('quiz_page'))
            pdf = _save_uploaded_pdf(upload, subject)
            if not pdf:
                flash('Could not extract text from PDF. The file may be scanned/image-based.', 'error')
                return redirect(url_for('quiz_page'))
        else:
            existing_id = request.form.get('existing_pdf_id')
            if existing_id:
                pdf = get_pdf(int(existing_id))

        if not pdf:
            flash('Please upload a PDF or select a previously uploaded one', 'error')
            return redirect(url_for('quiz_page'))

        source_pdf_id = pdf['id']
        page_mode = request.form.get('page_mode', 'entire')
        start_page = request.form.get('start_page', '').strip()
        end_page = request.form.get('end_page', '').strip()
        if page_mode == 'range' and (start_page or end_page):
            page_range = f"{start_page or 1}-{end_page or pdf['page_count']}"
            pdf_text = get_pdf_text_range(pdf, start_page or None, end_page or None)
        else:
            pdf_text = get_pdf_text_range(pdf)

        context_text = pdf_text
        if not topic.strip():
            topic = request.form.get('chapter_topic', '').strip() or pdf['original_name'].rsplit('.', 1)[0]
    elif not topic.strip():
        flash('Please enter a topic', 'error')
        return redirect(url_for('quiz_page'))

    try:
        questions = generate_exam_quiz(client, MODEL, topic, question_type, difficulty, count, context_text)
        quiz_id = save_quiz(subject, topic, difficulty, questions, question_type, source_pdf_id, page_range)
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
    attempt_id = submit_quiz(quiz_id, answers, time_taken, client=client, model=MODEL)
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


# ─── Smart Study Planner ─────────────────────────────────────────────

STUDY_MATERIAL_EXTS = ('.pdf', '.docx', '.txt')


def _extract_study_material(file):
    """Save an uploaded study material and extract its text. Returns a material dict or None."""
    if not file or not file.filename:
        return None
    if not file.filename.lower().endswith(STUDY_MATERIAL_EXTS):
        return None
    filename = secure_filename(file.filename)
    ext = filename.rsplit('.', 1)[-1].lower()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S%f')
    saved_name = f"{timestamp}_{filename}"
    filepath = os.path.join(UPLOAD_DIR, saved_name)
    file.save(filepath)

    text, pages = extract_any_text(filepath, filename)
    if not text.strip():
        return None
    return {'filename': saved_name, 'original_name': filename, 'file_type': ext, 'pages': pages, 'text': text}


@app.route('/study-plan', methods=['GET'])
def study_plan_page():
    plans = get_study_plans()
    return render_template('study_plan.html', plans=plans, active_page='study_plan')


@app.route('/study-plan/create', methods=['POST'])
def study_plan_create():
    subject = request.form.get('subject', '').strip()
    exam_date = request.form.get('exam_date', '').strip()
    daily_hours = float(request.form.get('daily_hours', 2) or 2)
    plan_type = request.form.get('plan_type', 'daily')
    manual_topics = request.form.get('topics', '').strip()

    if not subject or not exam_date:
        flash('Please enter a subject and exam date', 'error')
        return redirect(url_for('study_plan_page'))

    materials = []
    for f in request.files.getlist('materials'):
        m = _extract_study_material(f)
        if m:
            materials.append(m)

    if not materials and not manual_topics:
        flash('Please upload study materials or enter topics manually', 'error')
        return redirect(url_for('study_plan_page'))

    try:
        plan_id = create_smart_study_plan(client, MODEL, subject, exam_date, daily_hours,
                                          plan_type, materials, manual_topics)
        flash(f'Smart study plan created for "{subject}"', 'success')
        return redirect(url_for('study_plan_detail', plan_id=plan_id))
    except Exception as e:
        flash(f'Error creating study plan: {str(e)}', 'error')
        return redirect(url_for('study_plan_page'))


@app.route('/study-plan/<int:plan_id>')
def study_plan_detail(plan_id):
    plan = get_study_plan(plan_id)
    if not plan:
        flash('Plan not found', 'error')
        return redirect(url_for('study_plan_page'))
    stats = get_plan_summary_stats(plan_id)
    materials = get_study_materials(plan_id=plan_id)
    learn_tasks = [t for t in plan['tasks'] if t['task_type'] == 'learn']
    revision_tasks = [t for t in plan['tasks'] if t['task_type'] in ('revision_1', 'revision_2', 'revision_3', 'final_revision')]
    practice_tasks = [t for t in plan['tasks'] if t['task_type'] == 'practice_test']
    grouped_learn = group_tasks_for_display(learn_tasks, plan['plan_type'])
    return render_template('study_plan.html', plans=get_study_plans(),
                         selected_plan=plan, stats=stats, materials=materials,
                         grouped_learn=grouped_learn, revision_tasks=revision_tasks,
                         practice_tasks=practice_tasks, today_str=datetime.now().strftime('%Y-%m-%d'),
                         active_page='study_plan')


@app.route('/study-plan/<int:plan_id>/rebalance', methods=['POST'])
def study_plan_rebalance(plan_id):
    moved = rebalance_plan(plan_id)
    if moved:
        flash(f'Rebalanced plan: {moved} overdue task(s) rescheduled', 'success')
    else:
        flash('No overdue tasks to reschedule', 'info')
    return redirect(url_for('study_plan_detail', plan_id=plan_id))


@app.route('/study-plan/task/<int:task_id>/status', methods=['POST'])
def study_plan_task_status(task_id):
    status = request.form.get('status', 'not_started')
    plan_id = request.form.get('plan_id', type=int)
    update_task_status(task_id, status)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'ok'})
    return redirect(url_for('study_plan_detail', plan_id=plan_id) if plan_id else url_for('study_plan_page'))


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
    media_notes = get_all_media_notes()
    note_id = request.args.get('view')
    media_id = request.args.get('media')
    selected_note = get_note(int(note_id)) if note_id else None
    selected_media = get_media_note(int(media_id)) if media_id else None
    if selected_note:
        selected_note['content_html'] = markdown.markdown(
            selected_note['content'], extensions=['tables', 'fenced_code'])
    if selected_media:
        selected_media['notes_html'] = markdown.markdown(
            selected_media['notes'], extensions=['tables', 'fenced_code'])
        if selected_media.get('summary'):
            selected_media['summary_html'] = markdown.markdown(
                selected_media['summary'], extensions=['tables', 'fenced_code'])
        if selected_media.get('revision_notes'):
            selected_media['revision_html'] = markdown.markdown(
                selected_media['revision_notes'], extensions=['tables', 'fenced_code'])
        try:
            selected_media['full_data'] = json.loads(selected_media.get('full_data', '{}'))
        except (json.JSONDecodeError, TypeError):
            selected_media['full_data'] = {}
    return render_template('notes.html', notes=notes, media_notes=media_notes,
                         selected_note=selected_note, selected_media=selected_media,
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


@app.route('/notes/convert/media', methods=['POST'])
def notes_convert_media():
    if 'media_file' not in request.files:
        flash('No media file selected', 'error')
        return redirect(url_for('notes_page'))

    file = request.files['media_file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('notes_page'))

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in {'.mp3', '.wav', '.m4a', '.mp4', '.mkv', '.mov', '.avi', '.webm'}:
        flash('Please upload a supported audio/video file (MP3, WAV, M4A, MP4, MKV, MOV, AVI, WEBM)', 'error')
        return redirect(url_for('notes_page'))

    title = request.form.get('title', 'Untitled Media Notes')
    subject = request.form.get('subject', 'General')

    try:
        note_id = process_media_upload(file, title, subject, client, MODEL)
        flash(f'Media lecture converted: "{title}"', 'success')
        return redirect(url_for('notes_page', media=note_id))
    except Exception as e:
        app.logger.error(f'Media notes conversion error: {e}', exc_info=True)
        flash(f'Error converting media: {str(e)}', 'error')
        return redirect(url_for('notes_page'))


# ─── YouTube Video Analyzer ───────────────────────────────────────────

@app.route('/youtube', methods=['GET'])
def youtube_page():
    notes = get_all_youtube_notes()
    view_id = request.args.get('view')
    selected = get_youtube_note(int(view_id)) if view_id else None
    if selected:
        selected['notes_html'] = markdown.markdown(
            selected.get('notes', '') or '', extensions=['tables', 'fenced_code'])
        selected['summary_html'] = markdown.markdown(
            selected.get('summary', '') or '', extensions=['tables', 'fenced_code'])
        selected['revision_html'] = markdown.markdown(
            selected.get('revision_notes', '') or '', extensions=['tables', 'fenced_code'])
        selected['full_data'] = json.loads(selected.get('full_data', '{}') or '{}')
        selected['duration_formatted'] = _format_duration(selected.get('duration'))
        for q in selected.get('quiz', []):
            try:
                q['options'] = json.loads(q['options']) if q.get('options') else []
            except Exception:
                q['options'] = []
    return render_template('youtube.html', notes=notes, selected=selected, active_page='youtube')


@app.route('/youtube/analyze', methods=['POST'])
def youtube_analyze():
    url = request.form.get('video_url', '').strip()
    title = request.form.get('title', '').strip()
    subject = request.form.get('subject', 'General').strip()
    if not url:
        flash('Please enter a YouTube URL', 'error')
        return redirect(url_for('youtube_page'))
    if not title:
        title = 'Untitled YouTube Notes'
    try:
        note_id = process_youtube_url(url, title, subject, client, MODEL)
        flash('YouTube video analyzed successfully', 'success')
        return redirect(url_for('youtube_page', view=note_id))
    except Exception as e:
        app.logger.error(f'YouTube analysis error: {e}', exc_info=True)
        flash(f'Error analyzing YouTube video: {str(e)}', 'error')
        return redirect(url_for('youtube_page'))


@app.route('/youtube/create-plan', methods=['POST'])
def youtube_create_plan():
    note_id = request.form.get('note_id')
    subject = request.form.get('subject', 'General').strip()
    note = get_youtube_note(int(note_id)) if note_id else None
    if not note:
        flash('Video not found', 'error')
        return redirect(url_for('youtube_page'))
    topics = [t.get('topic_name', '') for t in note.get('topics', [])]
    if not topics:
        topics = [subject]
    exam_date = (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d')
    try:
        daily_hours = float(request.form.get('daily_hours', 1))
    except ValueError:
        daily_hours = 1.0
    try:
        plan_id = create_smart_study_plan(client, MODEL, subject, exam_date, daily_hours, 'topic', [], '\n'.join(topics))
        flash('Study plan created from YouTube video topics', 'success')
        return redirect(url_for('study_plan_detail', plan_id=plan_id))
    except Exception as e:
        app.logger.error(f'YouTube study plan creation error: {e}', exc_info=True)
        flash(f'Could not create study plan: {str(e)}', 'error')
        return redirect(url_for('youtube_page', view=note_id))


# ─── Exam Prediction Assistant ───────────────────────────────────────

ALLOWED_DOC_EXTS = ('.pdf', '.docx', '.txt')


def _save_exam_upload(file, subject, doc_type):
    """Save+extract text from an uploaded paper/question bank file. Returns doc_id or None."""
    if not file or not file.filename:
        return None
    if not file.filename.lower().endswith(ALLOWED_DOC_EXTS):
        return None
    filename = secure_filename(file.filename)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S%f')
    saved_name = f"{timestamp}_{filename}"
    filepath = os.path.join(UPLOAD_DIR, saved_name)
    file.save(filepath)

    text, _ = extract_any_text(filepath, filename)
    if not text.strip():
        return None
    year_match = re.search(r'(19|20)\d{2}', filename)
    year = year_match.group(0) if year_match else None
    return save_exam_document(subject, doc_type, saved_name, filename, text, year)


@app.route('/predict', methods=['GET'])
def predict_page():
    subject_filter = request.args.get('subject', '').strip() or None
    predictions = get_predictions(subject_filter)
    documents = get_exam_documents(subject_filter)
    return render_template('predict.html', predictions=predictions, documents=documents,
                         subject_filter=subject_filter, active_page='predict')


@app.route('/predict/analyze', methods=['POST'])
def predict_analyze():
    subject = request.form.get('subject', '').strip()
    syllabus = request.form.get('syllabus_topics', '').strip()
    analysis_type = request.form.get('analysis_type', 'full')

    if not subject:
        flash('Please enter a subject', 'error')
        return redirect(url_for('predict_page'))

    papers = request.files.getlist('papers')
    question_banks = request.files.getlist('question_banks')
    uploaded = 0
    for f in papers:
        if _save_exam_upload(f, subject, 'paper'):
            uploaded += 1
    for f in question_banks:
        if _save_exam_upload(f, subject, 'question_bank'):
            uploaded += 1

    try:
        data = analyze_exam_documents(client, MODEL, subject, analysis_type,
                                      syllabus if syllabus else None)
        pred_id = save_full_prediction(subject, analysis_type, data)
        log_study_session(subject, 'Exam Prediction', 8, 'analysis')
        msg = f'Exam analysis complete for "{subject}"'
        if uploaded:
            msg += f' ({uploaded} document{"s" if uploaded != 1 else ""} uploaded)'
        flash(msg, 'success')
        return redirect(url_for('predict_page', subject=subject) + f'#pred-{pred_id}')
    except Exception as e:
        flash(f'Error analyzing exam documents: {str(e)}', 'error')
        return redirect(url_for('predict_page', subject=subject))


@app.route('/predict/practice-test/<int:prediction_id>/<test_type>')
def predict_practice_test(prediction_id, test_type):
    prediction = get_prediction(prediction_id)
    if not prediction:
        flash('Prediction not found', 'error')
        return redirect(url_for('predict_page'))
    try:
        quiz_id = generate_practice_test(client, MODEL, prediction, test_type)
        flash(f'Practice test generated ({test_type.upper()})', 'success')
        return redirect(url_for('quiz_take', quiz_id=quiz_id))
    except Exception as e:
        flash(f'Error generating practice test: {str(e)}', 'error')
        return redirect(url_for('predict_page', subject=prediction.get('subject')))


@app.route('/predict/export/<int:prediction_id>/<fmt>')
def predict_export(prediction_id, fmt):
    if fmt not in ('txt', 'pdf'):
        return "Invalid format", 400
    prediction = get_prediction(prediction_id)
    if not prediction:
        flash('Prediction not found', 'error')
        return redirect(url_for('predict_page'))
    filepath = export_prediction(prediction, fmt)
    return send_file(filepath, as_attachment=True)


@app.route('/quiz/export/<int:quiz_id>/<fmt>')
def quiz_export(quiz_id, fmt):
    if fmt not in ('txt', 'pdf'):
        return "Invalid format", 400
    filepath = export_quiz(quiz_id, fmt)
    return send_file(filepath, as_attachment=True)


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

"""JSON REST API for the Intellect Flutter client."""
import os
import re
import json
import time
import logging
from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename

from exam_platform import (
    _get_conn, init_exam_db, _ai_call, convert_to_notes, save_notes,
    get_all_notes, get_note, get_dashboard_data, get_dashboard_study_overview, get_progress_data,
    get_all_quizzes, get_quiz, get_quiz_result, submit_quiz,
    get_flashcards, get_due_flashcards, update_flashcard_review, get_flashcard_stats,
    generate_flashcards, save_flashcards,
    generate_exam_quiz, save_quiz, get_quiz_history,
    get_study_plans, get_study_plan, create_smart_study_plan, update_task_status,
    rebalance_plan, get_plan_summary_stats,
    log_study_session, get_knowledge_documents, save_knowledge_document,
    extract_any_text, extract_pdf_text, save_pdf, get_pdfs, get_pdf, get_pdf_text_range,
    detect_weak_topics, get_all_mastery,
    get_exam_documents, analyze_exam_documents, save_full_prediction, get_predictions,
    UPLOAD_DIR
)
from pipeline import get_analytics, get_stream_stats
from media_notes import (
    process_media_upload, get_all_media_notes, get_media_note
)
from youtube_notes import (
    process_youtube_url, get_all_youtube_notes, get_youtube_note
)
from rag import query_knowledge

logger = logging.getLogger('api')
api_bp = Blueprint('api', __name__, url_prefix='/api/v1')


def _jsonify(data, status=200):
    resp = jsonify(data)
    resp.status_code = status
    return resp


def _ask_groq(client, model, question, context=None):
    start = time.time()
    messages = [{"role": "system", "content": "You are a helpful assistant. Give clear, concise answers."}]
    if context:
        messages.append({"role": "system", "content": f"Use this context:\n{context[:4000]}"})
    messages.append({"role": "user", "content": question})
    response = client.chat.completions.create(model=model, messages=messages)
    elapsed = time.time() - start
    raw = response.choices[0].message.content
    tokens = response.usage.total_tokens if response.usage else 0
    return raw, elapsed, tokens


@api_bp.route('/dashboard', methods=['GET'])
def api_dashboard():
    data = get_dashboard_data()
    data['study_overview'] = get_dashboard_study_overview()
    return _jsonify(data)


@api_bp.route('/ask', methods=['POST'])
def api_ask():
    data = request.get_json() or {}
    question = data.get('question', '').strip()
    subject = data.get('subject', '').strip()
    use_rag = data.get('use_rag', False)
    if not question:
        return _jsonify({'error': 'Question is required'}, 400)
    try:
        if use_rag and subject:
            chunks = query_knowledge(subject, question, top_k=5)
            if chunks:
                context = '\n\n---\n\n'.join(chunks)
                answer, elapsed, tokens = _ask_groq(current_app.config['GROQ_CLIENT'],
                                                     current_app.config['GROQ_MODEL'],
                                                     f"Answer based only on context.\n\nContext:\n{context[:4000]}\n\nQuestion: {question}")
            else:
                answer, elapsed, tokens = _ask_groq(current_app.config['GROQ_CLIENT'],
                                                     current_app.config['GROQ_MODEL'],
                                                     question)
        else:
            answer, elapsed, tokens = _ask_groq(current_app.config['GROQ_CLIENT'],
                                                 current_app.config['GROQ_MODEL'],
                                                 question)
        return _jsonify({'answer': answer, 'response_time': round(elapsed, 2), 'tokens': tokens})
    except Exception as e:
        logger.error(f'API ask error: {e}', exc_info=True)
        return _jsonify({'error': str(e)}, 500)


@api_bp.route('/notes', methods=['GET'])
def api_notes():
    return _jsonify({
        'lecture_notes': get_all_notes(),
        'media_notes': get_all_media_notes(),
        'youtube_notes': get_all_youtube_notes()
    })


@api_bp.route('/notes/<int:note_id>', methods=['GET'])
def api_note(note_id):
    note = get_note(note_id)
    if note:
        return _jsonify({'type': 'lecture', 'data': note})
    media = get_media_note(note_id)
    if media:
        try:
            media['full_data'] = json.loads(media.get('full_data', '{}') or '{}')
        except Exception:
            media['full_data'] = {}
        return _jsonify({'type': 'media', 'data': media})
    yt = get_youtube_note(note_id)
    if yt:
        try:
            yt['full_data'] = json.loads(yt.get('full_data', '{}') or '{}')
        except Exception:
            yt['full_data'] = {}
        for q in yt.get('quiz', []):
            try:
                q['options'] = json.loads(q['options']) if q.get('options') else []
            except Exception:
                q['options'] = []
        return _jsonify({'type': 'youtube', 'data': yt})
    return _jsonify({'error': 'Note not found'}, 404)


@api_bp.route('/notes/convert', methods=['POST'])
def api_notes_convert():
    data = request.get_json() or {}
    lecture_text = data.get('lecture_text', '').strip()
    subject = data.get('subject', 'General').strip()
    title = data.get('title', 'Untitled Notes').strip()
    if not lecture_text:
        return _jsonify({'error': 'lecture_text is required'}, 400)
    try:
        content = convert_to_notes(current_app.config['GROQ_CLIENT'],
                                   current_app.config['GROQ_MODEL'],
                                   lecture_text, subject, title)
        note_id = save_notes(subject, title, content, 'lecture')
        return _jsonify({'note_id': note_id, 'content': content})
    except Exception as e:
        logger.error(f'API notes convert error: {e}', exc_info=True)
        return _jsonify({'error': str(e)}, 500)


@api_bp.route('/notes/convert/media', methods=['POST'])
def api_notes_convert_media():
    if 'media_file' not in request.files:
        return _jsonify({'error': 'No media file'}, 400)
    file = request.files['media_file']
    if not file.filename:
        return _jsonify({'error': 'No file selected'}, 400)
    title = request.form.get('title', 'Untitled Media Notes')
    subject = request.form.get('subject', 'General')
    try:
        note_id = process_media_upload(file, title, subject,
                                       current_app.config['GROQ_CLIENT'],
                                       current_app.config['GROQ_MODEL'])
        return _jsonify({'note_id': note_id, 'type': 'media'})
    except Exception as e:
        logger.error(f'API media convert error: {e}', exc_info=True)
        return _jsonify({'error': str(e)}, 500)


@api_bp.route('/youtube/analyze', methods=['POST'])
def api_youtube_analyze():
    data = request.get_json() or {}
    url = data.get('video_url', '').strip()
    title = data.get('title', 'Untitled YouTube Notes').strip()
    subject = data.get('subject', 'General').strip()
    if not url:
        return _jsonify({'error': 'video_url is required'}, 400)
    try:
        note_id = process_youtube_url(url, title or 'Untitled YouTube Notes', subject,
                                      current_app.config['GROQ_CLIENT'],
                                      current_app.config['GROQ_MODEL'])
        return _jsonify({'note_id': note_id})
    except Exception as e:
        logger.error(f'API YouTube analysis error: {e}', exc_info=True)
        return _jsonify({'error': str(e)}, 500)


@api_bp.route('/youtube/<int:note_id>', methods=['GET'])
def api_youtube(note_id):
    yt = get_youtube_note(note_id)
    if not yt:
        return _jsonify({'error': 'Not found'}, 404)
    try:
        yt['full_data'] = json.loads(yt.get('full_data', '{}') or '{}')
    except Exception:
        yt['full_data'] = {}
    for q in yt.get('quiz', []):
        try:
            q['options'] = json.loads(q['options']) if q.get('options') else []
        except Exception:
            q['options'] = []
    return _jsonify(yt)


@api_bp.route('/quizzes', methods=['GET'])
def api_quizzes():
    return _jsonify(get_all_quizzes())


@api_bp.route('/quizzes/<int:quiz_id>', methods=['GET'])
def api_quiz(quiz_id):
    quiz = get_quiz(quiz_id)
    if not quiz:
        return _jsonify({'error': 'Quiz not found'}, 404)
    return _jsonify(quiz)


@api_bp.route('/quizzes/<int:quiz_id>/submit', methods=['POST'])
def api_quiz_submit(quiz_id):
    data = request.get_json() or {}
    answers = data.get('answers', {})
    try:
        result = submit_quiz(quiz_id, answers)
        return _jsonify(result)
    except Exception as e:
        logger.error(f'API quiz submit error: {e}', exc_info=True)
        return _jsonify({'error': str(e)}, 500)


@api_bp.route('/flashcards', methods=['GET'])
def api_flashcards():
    return _jsonify({'due': get_due_flashcards(), 'all': get_flashcards()})


@api_bp.route('/flashcards/<int:card_id>/review', methods=['POST'])
def api_flashcard_review(card_id):
    data = request.get_json() or {}
    try:
        update_flashcard_review(card_id, int(data.get('confidence', 0)))
        return _jsonify({'success': True})
    except Exception as e:
        return _jsonify({'error': str(e)}, 500)


@api_bp.route('/study-plans', methods=['GET', 'POST'])
def api_study_plans():
    if request.method == 'GET':
        return _jsonify(get_study_plans())
    data = request.get_json() or {}
    subject = data.get('subject', '').strip()
    topics = data.get('topics', [])
    daily_hours = float(data.get('daily_hours', 1))
    days = int(data.get('days', 14))
    if not subject:
        return _jsonify({'error': 'subject is required'}, 400)
    try:
        exam_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
        plan_id = create_smart_study_plan(current_app.config['GROQ_CLIENT'],
                                          current_app.config['GROQ_MODEL'],
                                          subject, exam_date, daily_hours,
                                          'topic', [], '\n'.join(str(t) for t in topics))
        return _jsonify({'plan_id': plan_id})
    except Exception as e:
        logger.error(f'API study plan create error: {e}', exc_info=True)
        return _jsonify({'error': str(e)}, 500)


@api_bp.route('/study-plans/<int:plan_id>', methods=['GET'])
def api_study_plan(plan_id):
    plan = get_study_plan(plan_id)
    if not plan:
        return _jsonify({'error': 'Plan not found'}, 404)
    return _jsonify(plan)


@api_bp.route('/progress', methods=['GET'])
def api_progress():
    data = get_progress_data()
    data['weak_topics'] = detect_weak_topics()
    data['mastery'] = get_all_mastery()
    return _jsonify(data)


@api_bp.route('/flashcards/generate', methods=['POST'])
def api_flashcards_generate():
    data = request.get_json() or {}
    topic = data.get('topic', '').strip()
    subject = data.get('subject', 'General').strip()
    count = int(data.get('count', 10))
    context = data.get('context', '').strip() or None
    if not topic:
        return _jsonify({'error': 'topic is required'}, 400)
    try:
        cards = generate_flashcards(current_app.config['GROQ_CLIENT'],
                                    current_app.config['GROQ_MODEL'],
                                    topic, count, context)
        saved = save_flashcards(subject, topic, cards)
        log_study_session(subject, topic, 5, 'flashcard')
        return _jsonify({'saved': saved, 'cards': cards})
    except Exception as e:
        logger.error(f'API flashcard gen error: {e}', exc_info=True)
        return _jsonify({'error': str(e)}, 500)


@api_bp.route('/quizzes/generate', methods=['POST'])
def api_quiz_generate():
    data = request.get_json() or {}
    topic = data.get('topic', '').strip()
    subject = data.get('subject', 'General').strip()
    difficulty = data.get('difficulty', 'medium')
    question_type = data.get('question_type', 'mcq')
    count = int(data.get('count', 10))
    context = data.get('context', '').strip() or None
    if not topic:
        return _jsonify({'error': 'topic is required'}, 400)
    try:
        questions = generate_exam_quiz(current_app.config['GROQ_CLIENT'],
                                       current_app.config['GROQ_MODEL'],
                                       topic, question_type, difficulty, count, context)
        quiz_id = save_quiz(subject, topic, difficulty, questions, question_type)
        return _jsonify({'quiz_id': quiz_id, 'question_count': len(questions)})
    except Exception as e:
        logger.error(f'API quiz gen error: {e}', exc_info=True)
        return _jsonify({'error': str(e)}, 500)


@api_bp.route('/quizzes/history', methods=['GET'])
def api_quiz_history():
    return _jsonify(get_quiz_history())


@api_bp.route('/quizzes/<int:quiz_id>/result/<int:attempt_id>', methods=['GET'])
def api_quiz_result(quiz_id, attempt_id):
    attempt, quiz, questions = get_quiz_result(attempt_id)
    if not attempt:
        return _jsonify({'error': 'Result not found'}, 404)
    return _jsonify({'attempt': attempt, 'quiz': quiz, 'questions': questions})


@api_bp.route('/pdfs', methods=['GET'])
def api_pdfs():
    return _jsonify(get_pdfs())


@api_bp.route('/pdfs/<int:pdf_id>', methods=['GET'])
def api_pdf(pdf_id):
    pdf = get_pdf(pdf_id)
    if not pdf:
        return _jsonify({'error': 'PDF not found'}, 404)
    return _jsonify(pdf)


@api_bp.route('/pdfs/upload', methods=['POST'])
def api_pdf_upload():
    if 'pdf_file' not in request.files:
        return _jsonify({'error': 'No file'}, 400)
    file = request.files['pdf_file']
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        return _jsonify({'error': 'Please upload a valid PDF file'}, 400)
    subject = request.form.get('subject', 'General')
    filename = secure_filename(file.filename)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    saved_name = f"{timestamp}_{filename}"
    filepath = os.path.join(UPLOAD_DIR, saved_name)
    file.save(filepath)
    text, page_count, page_texts = extract_pdf_text(filepath)
    if not text.strip():
        return _jsonify({'error': 'Could not extract text from PDF'}, 400)
    pdf_id = save_pdf(subject, saved_name, filename, text, page_count, page_texts)
    return _jsonify({'pdf_id': pdf_id, 'page_count': page_count, 'filename': filename})


@api_bp.route('/pdfs/<int:pdf_id>/ask', methods=['POST'])
def api_pdf_ask(pdf_id):
    pdf = get_pdf(pdf_id)
    if not pdf:
        return _jsonify({'error': 'PDF not found'}, 404)
    data = request.get_json() or {}
    question = data.get('question', '').strip()
    if not question:
        return _jsonify({'error': 'question is required'}, 400)
    try:
        answer, elapsed, tokens = _ask_groq(current_app.config['GROQ_CLIENT'],
                                             current_app.config['GROQ_MODEL'],
                                             question, context=pdf['extracted_text'])
        log_study_session(pdf.get('subject', 'General'), 'PDF Study', 3, 'reading')
        return _jsonify({'answer': answer, 'response_time': round(elapsed, 2)})
    except Exception as e:
        logger.error(f'API PDF ask error: {e}', exc_info=True)
        return _jsonify({'error': str(e)}, 500)


@api_bp.route('/visualize', methods=['POST'])
def api_visualize():
    data = request.get_json() or {}
    content = data.get('content', '').strip()
    diagram_type = data.get('diagram_type', 'mindmap')
    if not content:
        return _jsonify({'error': 'content is required'}, 400)
    try:
        prompt = f"""Convert the following explanation into a {diagram_type} using valid Mermaid syntax.
Write ONLY the Mermaid code. Do not include any explanation, markdown code fences, or thinking tags.

Diagram rules:
- mindmap: start with "mindmap" on its own line, then use "root((Topic))" and indented sub-items.
- flowchart: use "flowchart TD" and use arrows like "A[Start] --> B[Next]".
- concept: use "graph TD" with node names and "-->" links.
- process: use "flowchart LR" with steps linked by arrows.

Explanation:
{content[:4000]}"""
        raw = _ai_call(current_app.config['GROQ_CLIENT'],
                       current_app.config['GROQ_MODEL'],
                       'You are an expert at generating valid Mermaid diagrams. Return only the Mermaid code.',
                       prompt)
        raw = re.sub(r'\s*<\|/?think\|>\s*', '', raw)
        mermaid_code = re.sub(r'```(?:mermaid)?\s*|```', '', raw, flags=re.IGNORECASE).strip()
        mermaid_code = re.sub(r'^\s*mermaid\s*\n', '', mermaid_code, flags=re.IGNORECASE)
        return _jsonify({'mermaid_code': mermaid_code, 'diagram_type': diagram_type})
    except Exception as e:
        logger.error(f'API visualize error: {e}', exc_info=True)
        return _jsonify({'error': str(e)}, 500)


@api_bp.route('/analytics', methods=['GET'])
def api_analytics():
    data = get_analytics()
    stream = get_stream_stats()
    return _jsonify({'analytics': data, 'stream': stream})


@api_bp.route('/predict', methods=['POST'])
def api_predict():
    data = request.get_json() or {}
    subject = data.get('subject', '').strip()
    syllabus = data.get('syllabus_topics', '').strip()
    analysis_type = data.get('analysis_type', 'full')
    if not subject:
        return _jsonify({'error': 'subject is required'}, 400)
    try:
        result = analyze_exam_documents(current_app.config['GROQ_CLIENT'],
                                        current_app.config['GROQ_MODEL'],
                                        subject, analysis_type,
                                        syllabus if syllabus else None)
        pred_id = save_full_prediction(subject, analysis_type, result)
        log_study_session(subject, 'Exam Prediction', 8, 'analysis')
        return _jsonify({'prediction_id': pred_id, 'data': result})
    except Exception as e:
        logger.error(f'API predict error: {e}', exc_info=True)
        return _jsonify({'error': str(e)}, 500)


@api_bp.route('/predictions', methods=['GET'])
def api_predictions():
    subject = request.args.get('subject', '').strip() or None
    return _jsonify(get_predictions(subject))


@api_bp.route('/study-plans/<int:plan_id>/task/<int:task_id>', methods=['POST'])
def api_task_status(plan_id, task_id):
    data = request.get_json() or {}
    status = data.get('status', 'not_started')
    update_task_status(task_id, status)
    return _jsonify({'success': True})


@api_bp.route('/study-plans/<int:plan_id>/rebalance', methods=['POST'])
def api_rebalance(plan_id):
    moved = rebalance_plan(plan_id)
    return _jsonify({'moved': moved})


@api_bp.route('/progress/log', methods=['POST'])
def api_log_session():
    data = request.get_json() or {}
    subject = data.get('subject', '').strip()
    topic = data.get('topic', '').strip()
    duration = int(data.get('duration', 0))
    activity = data.get('activity_type', 'reading')
    if not subject or duration <= 0:
        return _jsonify({'error': 'subject and duration > 0 required'}, 400)
    log_study_session(subject, topic, duration, activity)
    return _jsonify({'success': True})


def register_api_routes(app, client, model):
    app.config.setdefault('GROQ_CLIENT', client)
    app.config.setdefault('GROQ_MODEL', model)
    app.register_blueprint(api_bp)

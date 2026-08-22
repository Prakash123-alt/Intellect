import os
import re
import json
import logging
import subprocess
from datetime import datetime
from werkzeug.utils import secure_filename

from imageio_ffmpeg import get_ffmpeg_exe
from exam_platform import _get_conn, _ai_call, _parse_json_response, convert_to_notes, UPLOAD_DIR

logger = logging.getLogger('media_notes')

AUDIO_EXTS = {'.mp3', '.wav', '.m4a'}
VIDEO_EXTS = {'.mp4', '.mkv', '.mov', '.avi', '.webm'}
ALLOWED_MEDIA = AUDIO_EXTS | VIDEO_EXTS


def _ffmpeg_path():
    try:
        return get_ffmpeg_exe()
    except Exception:
        return None


def _media_duration(path):
    ffmpeg = _ffmpeg_path()
    if not ffmpeg:
        return None
    try:
        result = subprocess.run(
            [ffmpeg, '-i', path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        err = result.stderr
        match = re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)', err)
        if match:
            h, m, s = match.groups()
            return int(h) * 3600 + int(m) * 60 + float(s)
    except Exception:
        logger.exception(f'Could not read duration for {path}')
    return None


def _extract_audio_to_mp3(input_path, output_mp3):
    ffmpeg = _ffmpeg_path()
    if not ffmpeg:
        raise RuntimeError('ffmpeg binary not found. Install imageio-ffmpeg.')
    cmd = [
        ffmpeg, '-y', '-i', input_path,
        '-vn', '-ar', '16000', '-ac', '1',
        '-b:a', '64k', '-f', 'mp3', output_mp3
    ]
    try:
        subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
    except subprocess.CalledProcessError as e:
        logger.error(f'ffmpeg error:\n{e.stderr}')
        err_text = (e.stderr or '').strip()
        if 'does not contain any stream' in err_text:
            raise RuntimeError('No audio stream found in the uploaded file.')
        # The actual error is usually at the end of stderr; the start is just a version banner.
        err_lines = err_text.splitlines()
        tail = '\n'.join(err_lines[-15:]) if len(err_lines) > 15 else err_text
        raise RuntimeError(f'Audio extraction failed: {tail}')


def _transcribe_mp3(mp3_path, client):
    with open(mp3_path, 'rb') as audio_file:
        resp = client.audio.transcriptions.create(
            file=(os.path.basename(mp3_path), audio_file),
            model='whisper-large-v3',
            response_format='json'
        )
    return resp.text if hasattr(resp, 'text') else str(resp)


def _generate_media_analysis(client, model, transcript, subject, title):
    max_chars = 25000
    prompt = f"""You are an expert educational assistant. Convert the following lecture transcript into a comprehensive, exam-ready study resource.

Subject: {subject}
Title: {title}

Transcript:
{transcript[:max_chars]}

Return ONLY a single JSON object with these keys:
- summary: 3-5 sentence overview
- notes: well-structured markdown notes with clear headers, bullet points, bold key terms, a "Key Takeaways" section and a "Quick Review Questions" section
- topics: array of objects with "name", "difficulty" (easy/medium/hard), "importance_score" (0.0-1.0)
- key_concepts: array of important concept strings
- definitions: array of objects with "term" and "definition"
- flashcards: array of objects with "question", "answer", "difficulty" (easy/medium/hard)
- quiz: array of objects with "question", "options" (4 strings for mcq, empty otherwise), "answer", "type" (mcq/1mark/2mark/5mark), "difficulty" (easy/medium/hard)
- revision_notes: concise bullet-point string for last-minute revision
- mind_map: markdown/mermaid-style mind map string
- knowledge_graph: object with "nodes" (array of names) and "edges" (array of [source, target] pairs)
- practice_test: array of objects with "question" and "marks" (1, 2 or 5)
- action_items: array of assignment/project/task strings

Use \\n for newlines inside string values. Do not wrap the JSON in markdown code blocks. Do not include any text outside the JSON object."""

    # First try: ask the model to emit a strict JSON object via response_format.
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {'role': 'system', 'content': 'You are an expert educational AI. Return only a single JSON object. No arrays at the top level, no markdown, no explanation.'},
                {'role': 'user', 'content': prompt}
            ],
            temperature=0.7,
            response_format={'type': 'json_object'}
        )
        raw = resp.choices[0].message.content
        analysis = _parse_json_response(raw)
    except Exception as e:
        logger.warning(f'JSON-object call failed or not supported ({e}), falling back to plain generation')
        raw = _ai_call(
            client,
            model,
            'You are an expert educational AI. Return strictly valid JSON. No markdown, no explanation.',
            prompt
        )
        analysis = _parse_json_response(raw)

    if not isinstance(analysis, dict):
        logger.error(f'AI response was not a JSON object (type: {type(analysis)}). Full response: {json.dumps(analysis)[:500]}')
        raise ValueError('AI did not return a valid JSON object for media analysis')
    return analysis


def process_media_upload(file, title, subject, client, model, user_id='default'):
    filename = secure_filename(file.filename)
    name, ext = os.path.splitext(filename)
    ext = ext.lower()
    if ext not in ALLOWED_MEDIA:
        raise ValueError(f'Unsupported file type: {ext}. Allowed: {ALLOWED_MEDIA}')

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    saved_name = f'{ts}_{filename}'
    input_path = os.path.join(UPLOAD_DIR, saved_name)
    file.save(input_path)

    duration = _media_duration(input_path)

    conn = _get_conn()
    c = conn.cursor()
    c.execute(
        '''INSERT INTO uploaded_media (user_id, file_name, file_type, duration, original_name)
           VALUES (?, ?, ?, ?, ?)''',
        (user_id, saved_name, ext.lstrip('.'), duration, filename)
    )
    media_id = c.lastrowid
    conn.commit()

    try:
        mp3_path = os.path.join(UPLOAD_DIR, f'{ts}_audio.mp3')
        _extract_audio_to_mp3(input_path, mp3_path)
        transcript = _transcribe_mp3(mp3_path, client)
    except Exception:
        conn.close()
        raise

    c.execute(
        'INSERT INTO transcripts (media_id, transcript) VALUES (?, ?)',
        (media_id, transcript)
    )
    conn.commit()

    try:
        analysis = _generate_media_analysis(client, model, transcript, subject, title)
    except Exception as e:
        logger.error(f'Structured AI analysis failed ({e}), falling back to plain note generation.')
        # Always produce usable notes from the transcript, even if the JSON pipeline fails.
        if transcript and transcript.strip():
            try:
                notes_md = convert_to_notes(client, model, transcript, subject, title)
            except Exception as conv_err:
                logger.error(f'Plain note generation also failed: {conv_err}')
                notes_md = f'## Transcript\n\n{transcript}\n\n_AI analysis could not be completed for this media._'
        else:
            notes_md = 'No speech detected in the uploaded media.'
        analysis = {
            'summary': '',
            'notes': notes_md,
            'topics': [],
            'key_concepts': [],
            'definitions': [],
            'flashcards': [],
            'quiz': [],
            'revision_notes': '',
            'mind_map': '',
            'knowledge_graph': {'nodes': [], 'edges': []},
            'practice_test': [],
            'action_items': []
        }

    notes = analysis.get('notes', '') or analysis.get('summary', '')
    summary = analysis.get('summary', '')
    revision = analysis.get('revision_notes', '')

    c.execute(
        '''INSERT INTO generated_notes
           (media_id, subject, title, notes, summary, revision_notes, full_data)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (media_id, subject, title, notes, summary, revision, json.dumps(analysis))
    )
    note_id = c.lastrowid
    conn.commit()

    for topic in analysis.get('topics', []):
        c.execute(
            '''INSERT INTO extracted_topics (media_id, topic_name, difficulty, importance_score)
               VALUES (?, ?, ?, ?)''',
            (
                media_id,
                topic.get('name', '') or 'Topic',
                topic.get('difficulty', 'medium'),
                topic.get('importance_score', 0)
            )
        )
    conn.commit()
    conn.close()
    return note_id


def get_all_media_notes():
    conn = _get_conn()
    c = conn.cursor()
    c.execute('''
        SELECT g.id, g.subject, g.title, 'media' as source_type,
               m.file_type, m.duration, g.created_at
        FROM generated_notes g
        JOIN uploaded_media m ON m.id = g.media_id
        ORDER BY g.created_at DESC
    ''')
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_media_note(note_id):
    conn = _get_conn()
    c = conn.cursor()
    c.execute('''
        SELECT g.id, g.media_id, g.subject, g.title, g.notes, g.summary,
               g.revision_notes, g.full_data, g.created_at,
               m.file_name, m.file_type, m.duration, m.original_name,
               t.transcript
        FROM generated_notes g
        JOIN uploaded_media m ON m.id = g.media_id
        LEFT JOIN transcripts t ON t.media_id = g.media_id
        WHERE g.id = ?
    ''', (note_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return None
    d = dict(row)
    c.execute(
        'SELECT topic_name, difficulty, importance_score FROM extracted_topics WHERE media_id = ?',
        (d['media_id'],)
    )
    d['topics'] = [dict(r) for r in c.fetchall()]
    conn.close()
    return d

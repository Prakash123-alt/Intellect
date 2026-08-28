import os
import re
import json
import math
import logging
import subprocess
from datetime import datetime

try:
    import yt_dlp
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:
    yt_dlp = None
    YouTubeTranscriptApi = None

try:
    from imageio_ffmpeg import get_ffmpeg_exe
except ImportError:
    def get_ffmpeg_exe():
        return None

from exam_platform import _get_conn, _ai_call, convert_to_notes, UPLOAD_DIR
from media_notes import _transcribe_mp3, _extract_audio_to_mp3, _generate_media_analysis, _media_duration

logger = logging.getLogger('youtube_notes')


def _video_id(url):
    """Extract an 11-char YouTube video ID from common URL forms."""
    if 'youtu.be' in url:
        return url.split('/')[-1].split('?')[0][:11]
    m = re.search(r'[?&]v=([0-9A-Za-z_-]{11})', url)
    if m:
        return m.group(1)
    m = re.search(r'embed/([0-9A-Za-z_-]{11})', url)
    if m:
        return m.group(1)
    raise ValueError('Invalid YouTube URL. Supported formats: youtube.com/watch?v=..., youtu.be/...')


def _format_duration(seconds):
    """Convert seconds to a human-readable duration string."""
    if not seconds:
        return 'Unknown'
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f'{h} Hour{"s" if h != 1 else ""}')
    if m:
        parts.append(f'{m} Minute{"s" if m != 1 else ""}')
    if s and not h:
        parts.append(f'{s} Second{"s" if s != 1 else ""}')
    return ' '.join(parts) if parts else 'Unknown'


def _fetch_metadata(url):
    """Fetch YouTube metadata using yt-dlp."""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return {
        'youtube_id': info.get('id'),
        'title': info.get('title', 'Untitled'),
        'channel_name': info.get('uploader', 'Unknown channel'),
        'duration': info.get('duration'),
        'upload_date': info.get('upload_date'),
        'description': info.get('description', '') or '',
    }


def _transcript_from_api(video_id):
    """Try to retrieve captions directly from YouTube."""
    try:
        chunks = YouTubeTranscriptApi.get_transcript(video_id)
        if chunks:
            return ' '.join(c.get('text', '') for c in chunks)
    except Exception as e:
        logger.info(f'Transcript API failed for {video_id}: {e}')
    return None


def _transcribe_large_mp3(mp3_path, client):
    """Split long MP3s into ~50-minute chunks to stay under Groq Whisper's 25 MB file limit."""
    ffmpeg = get_ffmpeg_exe()
    if not ffmpeg:
        raise RuntimeError('ffmpeg binary not found. Install imageio-ffmpeg.')

    duration = _media_duration(mp3_path)
    file_size_mb = os.path.getsize(mp3_path) / (1024 * 1024)

    # 64 kbps mono ~ 8 KB/s. Leave a margin for metadata/overhead.
    max_chunk_seconds = 3000
    if not duration or duration <= 0:
        # If duration unknown, attempt to transcribe as-is when the file is small.
        if file_size_mb <= 24:
            return _transcribe_mp3(mp3_path, client)
        raise RuntimeError('Could not determine audio duration; file is too large to transcribe safely.')

    num_chunks = max(1, math.ceil(duration / max_chunk_seconds))
    parts = []
    for i in range(num_chunks):
        start = i * max_chunk_seconds
        end = min(duration, (i + 1) * max_chunk_seconds)
        chunk_path = f'{mp3_path}.chunk_{i}.mp3'
        subprocess.run([
            ffmpeg, '-y', '-i', mp3_path,
            '-ss', str(start), '-t', str(end - start),
            '-c', 'copy', chunk_path
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True)
        parts.append(_transcribe_mp3(chunk_path, client))
        try:
            os.remove(chunk_path)
        except Exception:
            pass
    return ' '.join(parts)


def _transcript_from_audio(url, video_id, client):
    """Download audio with yt-dlp, convert to MP3, and transcribe with Groq Whisper."""
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    base_path = os.path.join(UPLOAD_DIR, f'{ts}_{video_id}')
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{base_path}.%(ext)s',
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
    downloaded = ydl.prepare_filename(info)
    if not os.path.exists(downloaded):
        raise RuntimeError('yt-dlp did not produce an audio file')

    mp3_path = f'{base_path}.mp3'
    _extract_audio_to_mp3(downloaded, mp3_path)
    transcript = _transcribe_large_mp3(mp3_path, client)
    return transcript, mp3_path


def process_youtube_url(url, title, subject, client, model, user_id='default'):
    """Fetch a YouTube video, extract or transcribe audio, and generate study materials."""
    youtube_id = _video_id(url)
    meta = _fetch_metadata(url)

    transcript = _transcript_from_api(youtube_id)
    audio_path = None
    if not transcript:
        transcript, audio_path = _transcript_from_audio(url, youtube_id, client)

    conn = _get_conn()
    c = conn.cursor()
    c.execute(
        '''INSERT INTO youtube_videos
           (user_id, video_url, youtube_id, title, channel_name, duration,
            upload_date, description, transcript, audio_path)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (user_id, url, youtube_id, meta['title'], meta['channel_name'],
         meta['duration'], meta['upload_date'], meta['description'],
         transcript, audio_path)
    )
    video_db_id = c.lastrowid
    conn.commit()

    try:
        analysis = _generate_media_analysis(client, model, transcript, subject, title)
    except Exception as e:
        logger.error(f'Structured AI analysis failed ({e}), falling back to plain notes.')
        if transcript and transcript.strip():
            try:
                notes_md = convert_to_notes(client, model, transcript, subject, title)
            except Exception as conv_err:
                logger.error(f'Plain note generation also failed: {conv_err}')
                notes_md = f'## Transcript\n\n{transcript}\n\n_AI analysis could not be completed for this video._'
        else:
            notes_md = 'No transcript could be extracted from this video.'
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
        '''INSERT INTO youtube_notes
           (video_id, subject, title, notes, summary, revision_notes, full_data)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (video_db_id, subject, title, notes, summary, revision, json.dumps(analysis))
    )
    note_id = c.lastrowid

    for q in analysis.get('quiz', []):
        c.execute(
            '''INSERT INTO youtube_quizzes
               (video_id, question, question_type, options, answer, explanation, difficulty, marks)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (video_db_id,
             q.get('question', ''),
             q.get('type', 'mcq'),
             json.dumps(q.get('options', [])),
             q.get('answer', ''),
             q.get('explanation', ''),
             q.get('difficulty', 'medium'),
             q.get('marks', 1) or 1)
        )

    for t in analysis.get('topics', []):
        c.execute(
            '''INSERT INTO youtube_topics
               (video_id, topic_name, difficulty, importance_score)
               VALUES (?, ?, ?, ?)''',
            (video_db_id,
             t.get('name', ''),
             t.get('difficulty', 'medium'),
             t.get('importance_score', 0))
        )

    conn.commit()
    conn.close()
    return note_id


def get_all_youtube_notes():
    conn = _get_conn()
    c = conn.cursor()
    c.execute('''
        SELECT n.id, n.subject, n.title, v.duration, n.created_at
        FROM youtube_notes n
        JOIN youtube_videos v ON v.id = n.video_id
        ORDER BY n.created_at DESC
    ''')
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_youtube_note(note_id):
    conn = _get_conn()
    c = conn.cursor()
    c.execute('''
        SELECT n.id, n.video_id, n.subject, n.title, n.notes, n.summary,
               n.revision_notes, n.full_data, n.created_at,
               v.video_url, v.youtube_id, v.title as video_title,
               v.channel_name, v.duration, v.upload_date, v.description, v.transcript
        FROM youtube_notes n
        JOIN youtube_videos v ON v.id = n.video_id
        WHERE n.id = ?
    ''', (note_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return None
    d = dict(row)
    c.execute('SELECT topic_name, difficulty, importance_score FROM youtube_topics WHERE video_id = ?', (d['video_id'],))
    d['topics'] = [dict(r) for r in c.fetchall()]
    c.execute('SELECT question, question_type, options, answer, explanation, difficulty, marks FROM youtube_quizzes WHERE video_id = ?', (d['video_id'],))
    d['quiz'] = [dict(r) for r in c.fetchall()]
    conn.close()
    return d

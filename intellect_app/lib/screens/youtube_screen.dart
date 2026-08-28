import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import '../services/api_service.dart';

class YouTubeScreen extends StatefulWidget {
  const YouTubeScreen({super.key});

  @override
  State<YouTubeScreen> createState() => _YouTubeScreenState();
}

class _YouTubeScreenState extends State<YouTubeScreen> {
  final _urlCtrl = TextEditingController();
  final _titleCtrl = TextEditingController();
  final _subjectCtrl = TextEditingController();
  bool _analyzing = false;
  bool _loading = true;
  List<dynamic> _ytNotes = [];
  Map<String, dynamic>? _selectedNote;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final data = await ApiService.get('/notes');
      setState(() { _ytNotes = data['youtube_notes'] ?? []; _loading = false; });
    } catch (e) {
      setState(() => _loading = false);
    }
  }

  Future<void> _analyze() async {
    if (_urlCtrl.text.trim().isEmpty) return;
    setState(() => _analyzing = true);
    try {
      final data = await ApiService.post('/youtube/analyze', {
        'video_url': _urlCtrl.text.trim(),
        'title': _titleCtrl.text.trim().isNotEmpty ? _titleCtrl.text.trim() : 'YouTube Notes',
        'subject': _subjectCtrl.text.trim().isNotEmpty ? _subjectCtrl.text.trim() : 'General',
      });
      if (mounted) {
        _urlCtrl.clear(); _titleCtrl.clear(); _subjectCtrl.clear();
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Analysis complete!'), backgroundColor: Color(0xFF065F46)));
        await _load();
        _view(data['note_id']);
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red));
    } finally {
      setState(() => _analyzing = false);
    }
  }

  Future<void> _view(int noteId) async {
    try {
      final data = await ApiService.get('/youtube/$noteId');
      setState(() => _selectedNote = data);
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_selectedNote != null ? 'YouTube Notes' : 'YouTube Analyzer'),
        leading: _selectedNote != null ? IconButton(icon: const Icon(Icons.arrow_back), onPressed: () => setState(() => _selectedNote = null)) : IconButton(icon: const Icon(Icons.menu), onPressed: () => Scaffold.of(context).openDrawer()),
      ),
      body: _selectedNote != null ? _buildDetail() : _buildMain(),
    );
  }

  Widget _buildMain() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Card(child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('Analyze YouTube Video', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: Colors.white)),
            TextField(controller: _urlCtrl, decoration: const InputDecoration(labelText: 'YouTube URL', isDense: true, hintText: 'https://youtube.com/watch?v=...')),
            const SizedBox(height: 10),
            TextField(controller: _titleCtrl, decoration: const InputDecoration(labelText: 'Title (optional)', isDense: true)),
            const SizedBox(height: 10),
            TextField(controller: _subjectCtrl, decoration: const InputDecoration(labelText: 'Subject (optional)', isDense: true)),
            const SizedBox(height: 12),
            SizedBox(width: double.infinity, child: ElevatedButton.icon(
              onPressed: _analyzing ? null : _analyze,
              icon: _analyzing ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)) : const Icon(Icons.play_arrow, size: 18),
              label: Text(_analyzing ? 'Analyzing...' : 'Analyze Video'),
            )),
          ]),
        )),
        const SizedBox(height: 20),
        if (_loading) const Center(child: CircularProgressIndicator(color: Color(0xFFA855F7)))
        else if (_ytNotes.isNotEmpty) ...[
          Text('Previous (${_ytNotes.length})', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: Colors.white)),
          const SizedBox(height: 12),
          ..._ytNotes.map((n) => Card(child: ListTile(
            leading: const Icon(Icons.video_library, color: Color(0xFFA855F7)),
            title: Text(n['title'] ?? 'Video', style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
            subtitle: Text(n['subject'] ?? '', style: const TextStyle(fontSize: 12, color: Color(0xFF64748B))),
            onTap: () => _view(n['id']),
          ))),
        ],
      ]),
    );
  }

  Widget _buildDetail() {
    final notes = _selectedNote?['notes'] ?? _selectedNote?['full_data']?['notes'] ?? '';
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(_selectedNote?['title'] ?? 'Video Notes', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700, color: Colors.white)),
        const SizedBox(height: 4),
        Text(_selectedNote?['subject'] ?? '', style: const TextStyle(fontSize: 13, color: Color(0xFF94A3B8))),
        const Divider(color: Color(0xFF1E2235), height: 24),
        MarkdownBody(data: notes, styleSheet: MarkdownStyleSheet(
          p: const TextStyle(color: Color(0xFFCBD5E1), fontSize: 14, height: 1.7),
          h1: const TextStyle(color: Color(0xFFE2E8F0), fontSize: 20, fontWeight: FontWeight.w700),
          h2: const TextStyle(color: Color(0xFFE2E8F0), fontSize: 18, fontWeight: FontWeight.w700),
          strong: const TextStyle(color: Color(0xFFE2E8F0), fontWeight: FontWeight.w700),
        )),
      ]),
    );
  }
}

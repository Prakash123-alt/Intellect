import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import '../services/api_service.dart';

class NotesScreen extends StatefulWidget {
  const NotesScreen({super.key});

  @override
  State<NotesScreen> createState() => _NotesScreenState();
}

class _NotesScreenState extends State<NotesScreen> {
  List<Map<String, dynamic>> _notes = [];
  bool _loading = true;
  bool _creating = false;
  Map<String, dynamic>? _selectedNote;
  final _titleCtrl = TextEditingController();
  final _subjectCtrl = TextEditingController();
  final _textCtrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final data = await ApiService.get('/notes');
      final notes = <Map<String, dynamic>>[];
      for (var n in (data['lecture_notes'] ?? [])) notes.add({...n, 'type': 'Lecture'});
      for (var n in (data['media_notes'] ?? [])) notes.add({...n, 'type': 'Media'});
      for (var n in (data['youtube_notes'] ?? [])) notes.add({...n, 'type': 'YouTube'});
      notes.sort((a, b) => (b['created_at'] ?? '').compareTo(a['created_at'] ?? ''));
      setState(() { _notes = notes; _loading = false; });
    } catch (e) {
      setState(() => _loading = false);
    }
  }

  Future<void> _view(Map<String, dynamic> note) async {
    try {
      final data = await ApiService.get('/notes/${note['id']}');
      setState(() => _selectedNote = data['data'] ?? data);
    } catch (_) {}
  }

  Future<void> _create() async {
    if (_textCtrl.text.trim().isEmpty || _titleCtrl.text.trim().isEmpty) return;
    setState(() => _creating = true);
    try {
      await ApiService.post('/notes/convert', {
        'lecture_text': _textCtrl.text.trim(),
        'subject': _subjectCtrl.text.trim().isNotEmpty ? _subjectCtrl.text.trim() : 'General',
        'title': _titleCtrl.text.trim(),
      });
      if (mounted) {
        _titleCtrl.clear(); _subjectCtrl.clear(); _textCtrl.clear();
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Notes created!'), backgroundColor: Color(0xFF065F46)));
        await _load();
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red));
    } finally {
      setState(() => _creating = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_selectedNote != null ? 'Note' : 'Notes'),
        leading: _selectedNote != null ? IconButton(icon: const Icon(Icons.arrow_back), onPressed: () => setState(() => _selectedNote = null)) : IconButton(icon: const Icon(Icons.menu), onPressed: () => Scaffold.of(context).openDrawer()),
      ),
      body: _selectedNote != null ? _buildDetail() : _buildList(),
    );
  }

  Widget _buildList() {
    if (_loading) return const Center(child: CircularProgressIndicator(color: Color(0xFFA855F7)));
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Card(child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('Convert to Notes', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: Colors.white)),
            TextField(controller: _titleCtrl, decoration: const InputDecoration(labelText: 'Title', isDense: true)),
            const SizedBox(height: 10),
            TextField(controller: _subjectCtrl, decoration: const InputDecoration(labelText: 'Subject', isDense: true)),
            const SizedBox(height: 10),
            TextField(controller: _textCtrl, decoration: const InputDecoration(labelText: 'Paste lecture text...', isDense: true), maxLines: 5),
            const SizedBox(height: 12),
            SizedBox(width: double.infinity, child: ElevatedButton.icon(onPressed: _creating ? null : _create, icon: _creating ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)) : const Icon(Icons.auto_awesome, size: 18), label: Text(_creating ? 'Converting...' : 'Convert to Notes'))),
          ]),
        )),
        const SizedBox(height: 20),
        if (_notes.isNotEmpty) ...[
          Text('All Notes (${_notes.length})', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: Colors.white)),
          const SizedBox(height: 12),
          ..._notes.map((n) => Card(child: ListTile(
            leading: Icon(n['type'] == 'YouTube' ? Icons.video_library : n['type'] == 'Media' ? Icons.audiotrack : Icons.edit_note, color: const Color(0xFFA855F7)),
            title: Text(n['title'] ?? 'Untitled', style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
            subtitle: Text('${n['subject'] ?? ''} • ${n['type']}', style: const TextStyle(fontSize: 12, color: Color(0xFF64748B))),
            trailing: const Icon(Icons.chevron_right, color: Color(0xFF64748B)),
            onTap: () => _view(n),
          ))),
        ] else
          const Center(child: Text('No notes yet', style: TextStyle(color: Color(0xFF64748B)))),
      ]),
    );
  }

  Widget _buildDetail() {
    final content = _selectedNote?['content'] ?? _selectedNote?['notes'] ?? '';
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(_selectedNote?['title'] ?? 'Note', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700, color: Colors.white)),
        Text(_selectedNote?['subject'] ?? '', style: const TextStyle(fontSize: 13, color: Color(0xFF94A3B8))),
        const Divider(color: Color(0xFF1E2235), height: 24),
        MarkdownBody(data: content, styleSheet: MarkdownStyleSheet(
          p: const TextStyle(color: Color(0xFFCBD5E1), fontSize: 14, height: 1.7),
          h1: const TextStyle(color: Color(0xFFE2E8F0), fontSize: 20, fontWeight: FontWeight.w700),
          h2: const TextStyle(color: Color(0xFFE2E8F0), fontSize: 18, fontWeight: FontWeight.w700),
          h3: const TextStyle(color: Color(0xFFE2E8F0), fontSize: 16, fontWeight: FontWeight.w700),
          strong: const TextStyle(color: Color(0xFFE2E8F0), fontWeight: FontWeight.w700),
          code: TextStyle(color: const Color(0xFFA855F7), backgroundColor: const Color(0xFF0B0D1A), fontSize: 13),
        )),
      ]),
    );
  }
}

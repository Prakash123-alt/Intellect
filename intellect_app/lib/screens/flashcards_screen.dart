import 'package:flutter/material.dart';
import '../services/api_service.dart';

class FlashcardsScreen extends StatefulWidget {
  const FlashcardsScreen({super.key});

  @override
  State<FlashcardsScreen> createState() => _FlashcardsScreenState();
}

class _FlashcardsScreenState extends State<FlashcardsScreen> {
  List<dynamic> _allCards = [];
  List<dynamic> _dueCards = [];
  bool _loading = true;
  bool _generating = false;
  int _currentIndex = 0;
  bool _showAnswer = false;
  final _topicCtrl = TextEditingController();
  final _subjectCtrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final data = await ApiService.get('/flashcards');
      setState(() { _allCards = data['all'] ?? []; _dueCards = data['due'] ?? []; _loading = false; });
    } catch (e) {
      setState(() => _loading = false);
    }
  }

  Future<void> _generate() async {
    if (_topicCtrl.text.trim().isEmpty) return;
    setState(() => _generating = true);
    try {
      final data = await ApiService.post('/flashcards/generate', {
        'topic': _topicCtrl.text.trim(),
        'subject': _subjectCtrl.text.trim().isNotEmpty ? _subjectCtrl.text.trim() : 'General',
        'count': 10,
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Generated ${data['saved']} flashcards'), backgroundColor: const Color(0xFF065F46)));
        _topicCtrl.clear();
        await _load();
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red));
    } finally {
      setState(() => _generating = false);
    }
  }

  Future<void> _review(int cardId, int confidence) async {
    try {
      await ApiService.post('/flashcards/$cardId/review', {'confidence': confidence});
      setState(() {
        _dueCards.removeAt(_currentIndex);
        if (_currentIndex >= _dueCards.length) _currentIndex = 0;
        _showAnswer = false;
      });
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Flashcards'), leading: IconButton(icon: const Icon(Icons.menu), onPressed: () => Scaffold.of(context).openDrawer())),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: Color(0xFFA855F7)))
          : SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Card(child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    const Text('Generate Flashcards', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: Colors.white)),
                    const SizedBox(height: 12),
                    TextField(controller: _topicCtrl, decoration: const InputDecoration(labelText: 'Topic', isDense: true, hintText: 'e.g. Photosynthesis')),
                    const SizedBox(height: 10),
                    TextField(controller: _subjectCtrl, decoration: const InputDecoration(labelText: 'Subject', isDense: true, hintText: 'e.g. Biology')),
                    const SizedBox(height: 12),
                    SizedBox(width: double.infinity, child: ElevatedButton.icon(
                      onPressed: _generating ? null : _generate,
                      icon: _generating ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)) : const Icon(Icons.auto_awesome, size: 18),
                      label: Text(_generating ? 'Generating...' : 'Generate'),
                    )),
                  ]),
                )),
                const SizedBox(height: 20),
                Row(children: [
                  _stat('Total', _allCards.length.toString(), const Color(0xFFA855F7)),
                  const SizedBox(width: 10),
                  _stat('Due', _dueCards.length.toString(), const Color(0xFFF59E0B)),
                ]),
                const SizedBox(height: 20),
                if (_dueCards.isNotEmpty) ...[
                  const Text('Review Due Cards', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: Colors.white)),
                  const SizedBox(height: 12),
                  _buildCard(),
                ] else if (_allCards.isNotEmpty) ...[
                  const Text('All Flashcards', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: Colors.white)),
                  const SizedBox(height: 12),
                  ..._allCards.take(20).map((c) => Card(child: ListTile(
                    title: Text(c['front'] ?? '', style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
                    subtitle: Text(c['back'] ?? '', maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 12, color: Color(0xFF94A3B8))),
                  ))),
                ] else
                  const Center(child: Text('No flashcards yet. Generate some above!', style: TextStyle(color: Color(0xFF64748B)))),
              ]),
            ),
    );
  }

  Widget _buildCard() {
    if (_currentIndex >= _dueCards.length) return const SizedBox();
    final card = _dueCards[_currentIndex];
    return GestureDetector(
      onTap: () => setState(() => _showAnswer = !_showAnswer),
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(gradient: const LinearGradient(colors: [Color(0xFF1a1040), Color(0xFF131629)], begin: Alignment.topLeft, end: Alignment.bottomRight), borderRadius: BorderRadius.circular(16), border: Border.all(color: const Color(0xFF7C3AED).withAlpha(100))),
        child: Column(children: [
          Text(_showAnswer ? (card['back'] ?? '') : (card['front'] ?? ''), textAlign: TextAlign.center, style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: _showAnswer ? const Color(0xFF22C55E) : Colors.white)),
          const SizedBox(height: 8),
          Text(_showAnswer ? 'Tap to flip' : 'Tap to reveal answer', style: const TextStyle(fontSize: 12, color: Color(0xFF64748B))),
          if (_showAnswer) ...[
            const SizedBox(height: 16),
            Row(mainAxisAlignment: MainAxisAlignment.spaceEvenly, children: [
              _confBtn('Hard', 1, Colors.red),
              _confBtn('Medium', 3, Colors.orange),
              _confBtn('Easy', 5, Colors.green),
            ]),
          ],
        ]),
      ),
    );
  }

  Widget _confBtn(String label, int conf, Color color) {
    final card = _dueCards[_currentIndex];
    return ElevatedButton(
      style: ElevatedButton.styleFrom(backgroundColor: color.withAlpha(50), foregroundColor: color, padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8)),
      onPressed: () => _review(card['id'], conf),
      child: Text(label, style: const TextStyle(fontSize: 12)),
    );
  }

  Widget _stat(String label, String value, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: BoxDecoration(color: const Color(0xFF131629), borderRadius: BorderRadius.circular(8), border: Border.all(color: const Color(0xFF1E2235))),
      child: Row(children: [
        Text(value, style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: color)),
        const SizedBox(width: 6),
        Text(label, style: const TextStyle(fontSize: 12, color: Color(0xFF94A3B8))),
      ]),
    );
  }
}

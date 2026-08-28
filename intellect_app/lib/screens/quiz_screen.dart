import 'package:flutter/material.dart';
import '../services/api_service.dart';

class QuizScreen extends StatefulWidget {
  const QuizScreen({super.key});

  @override
  State<QuizScreen> createState() => _QuizScreenState();
}

class _QuizScreenState extends State<QuizScreen> {
  List<dynamic> _quizzes = [];
  bool _loading = true;
  bool _generating = false;
  Map<String, dynamic>? _activeQuiz;
  List<dynamic>? _activeQuestions;
  Map<int, String> _answers = {};
  Map<String, dynamic>? _result;
  final _topicCtrl = TextEditingController();
  final _subjectCtrl = TextEditingController();
  String _difficulty = 'medium';
  String _type = 'mcq';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final data = await ApiService.get('/quizzes');
      setState(() { _quizzes = data is List ? data : []; _loading = false; });
    } catch (e) {
      setState(() => _loading = false);
    }
  }

  Future<void> _generate() async {
    if (_topicCtrl.text.trim().isEmpty) return;
    setState(() => _generating = true);
    try {
      final data = await ApiService.post('/quizzes/generate', {
        'topic': _topicCtrl.text.trim(),
        'subject': _subjectCtrl.text.trim().isNotEmpty ? _subjectCtrl.text.trim() : 'General',
        'difficulty': _difficulty,
        'question_type': _type,
        'count': 10,
      });
      if (mounted) {
        _topicCtrl.clear();
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Quiz created: ${data['question_count']} questions'), backgroundColor: const Color(0xFF065F46)));
        await _load();
        _takeQuiz(data['quiz_id']);
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red));
    } finally {
      setState(() => _generating = false);
    }
  }

  Future<void> _takeQuiz(int quizId) async {
    try {
      final data = await ApiService.get('/quizzes/$quizId');
      setState(() {
        _activeQuiz = data is Map<String, dynamic> ? data : {'questions': []};
        _activeQuestions = _activeQuiz!['questions'] ?? [];
        _answers = {}; _result = null;
      });
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red));
    }
  }

  Future<void> _submit(int quizId) async {
    try {
      final data = await ApiService.post('/quizzes/$quizId/submit', {
        'answers': _answers.map((k, v) => MapEntry(k.toString(), v)),
      });
      setState(() => _result = data);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_activeQuiz != null ? 'Take Quiz' : 'Quiz'),
        leading: _activeQuiz != null ? IconButton(icon: const Icon(Icons.arrow_back), onPressed: () => setState(() { _activeQuiz = null; _result = null; _answers = {}; })) : IconButton(icon: const Icon(Icons.menu), onPressed: () => Scaffold.of(context).openDrawer()),
      ),
      body: _activeQuiz != null ? _buildTaking() : _buildList(),
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
            const Text('Generate Quiz', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: Colors.white)),
            TextField(controller: _topicCtrl, decoration: const InputDecoration(labelText: 'Topic', isDense: true)),
            const SizedBox(height: 10),
            TextField(controller: _subjectCtrl, decoration: const InputDecoration(labelText: 'Subject', isDense: true)),
            const SizedBox(height: 10),
            Row(children: [
              Expanded(child: DropdownButtonFormField<String>(value: _difficulty, decoration: const InputDecoration(labelText: 'Difficulty', isDense: true), dropdownColor: const Color(0xFF131629), items: ['easy', 'medium', 'hard'].map((d) => DropdownMenuItem(value: d, child: Text(d))).toList(), onChanged: (v) => _difficulty = v ?? 'medium')),
              const SizedBox(width: 10),
              Expanded(child: DropdownButtonFormField<String>(value: _type, decoration: const InputDecoration(labelText: 'Type', isDense: true), dropdownColor: const Color(0xFF131629), items: const [DropdownMenuItem(value: 'mcq', child: Text('MCQ')), DropdownMenuItem(value: 'true_false', child: Text('TF')), DropdownMenuItem(value: 'short', child: Text('Short'))], onChanged: (v) => _type = v ?? 'mcq')),
            ]),
            const SizedBox(height: 12),
            SizedBox(width: double.infinity, child: ElevatedButton.icon(
              onPressed: _generating ? null : _generate,
              icon: _generating ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)) : const Icon(Icons.quiz, size: 18),
              label: Text(_generating ? 'Generating...' : 'Generate Quiz'),
            )),
          ]),
        )),
        const SizedBox(height: 20),
        if (_quizzes.isNotEmpty) ...[
          const Text('Your Quizzes', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: Colors.white)),
          const SizedBox(height: 12),
          ..._quizzes.map((q) => Card(child: ListTile(
            title: Text(q['topic'] ?? 'Quiz', style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
            subtitle: Text('${q['difficulty'] ?? 'medium'} • ${q['question_count'] ?? 0} q', style: const TextStyle(fontSize: 12, color: Color(0xFF64748B))),
            trailing: const Icon(Icons.play_arrow, color: Color(0xFFA855F7)),
            onTap: () => _takeQuiz(q['id']),
          ))),
        ],
      ]),
    );
  }

  Widget _buildTaking() {
    if (_result != null) return _buildResult();
    if (_activeQuestions == null || _activeQuestions!.isEmpty) return const Center(child: Text('No questions'));
    return Column(children: [
      Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        color: const Color(0xFF131629),
        child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
          Text('${_answers.length}/${_activeQuestions!.length} answered', style: const TextStyle(fontSize: 13, color: Color(0xFF94A3B8))),
          ElevatedButton(onPressed: _answers.length == _activeQuestions!.length ? () => _submit(_activeQuiz!['id'] ?? _activeQuiz!['quiz_id'] ?? 0) : null, child: const Text('Submit')),
        ]),
      ),
      Expanded(
        child: ListView.builder(
          padding: const EdgeInsets.all(16),
          itemCount: _activeQuestions!.length,
          itemBuilder: (ctx, i) {
            final q = _activeQuestions![i];
            final options = q['options'] is List ? q['options'] as List : [];
            return Card(
              margin: const EdgeInsets.only(bottom: 16),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('Q${i + 1}. ${q['question'] ?? ''}', style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: Colors.white)),
                  const SizedBox(height: 12),
                  ...options.asMap().entries.map((e) {
                    final label = String.fromCharCode(65 + e.key);
                    final selected = _answers[i] == label;
                    return GestureDetector(
                      onTap: () => setState(() => _answers[i] = label),
                      child: Container(
                        margin: const EdgeInsets.only(bottom: 8),
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(color: selected ? const Color(0xFF1a1040) : const Color(0xFF0B0D1A), borderRadius: BorderRadius.circular(8), border: Border.all(color: selected ? const Color(0xFF7C3AED) : const Color(0xFF1E2235))),
                        child: Row(children: [
                          Container(width: 24, height: 24, alignment: Alignment.center, decoration: BoxDecoration(shape: BoxShape.circle, color: selected ? const Color(0xFF7C3AED) : Colors.transparent, border: Border.all(color: selected ? const Color(0xFF7C3AED) : const Color(0xFF475569))), child: Text(label, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: selected ? Colors.white : const Color(0xFF94A3B8)))),
                          const SizedBox(width: 10),
                          Expanded(child: Text(e.value.toString(), style: TextStyle(fontSize: 13, color: selected ? Colors.white : const Color(0xFFCBD5E1)))),
                        ]),
                      ),
                    );
                  }),
                ]),
              ),
            );
          },
        ),
      ),
    ]);
  }

  Widget _buildResult() {
    final score = _result?['score'] ?? 0;
    final total = _result?['total'] ?? _activeQuestions?.length ?? 0;
    final pct = total > 0 ? (score / total * 100).round() : 0;
    return Center(
      child: Card(
        margin: const EdgeInsets.all(24),
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(pct >= 70 ? Icons.emoji_events : Icons.sentiment_neutral, size: 48, color: pct >= 70 ? const Color(0xFF22C55E) : const Color(0xFFF59E0B)),
              const SizedBox(height: 16),
              Text('$pct%', style: TextStyle(fontSize: 36, fontWeight: FontWeight.w800, color: pct >= 70 ? const Color(0xFF22C55E) : const Color(0xFFF59E0B))),
              Text('$score / $total correct', style: const TextStyle(fontSize: 14, color: Color(0xFF94A3B8))),
              const SizedBox(height: 24),
              ElevatedButton(onPressed: () => setState(() { _activeQuiz = null; _result = null; _answers = {}; }), child: const Text('Back to Quizzes')),
            ],
          ),
        ),
      ),
    );
  }
}

import 'package:flutter/material.dart';
import '../services/api_service.dart';

class ProgressScreen extends StatefulWidget {
  const ProgressScreen({super.key});

  @override
  State<ProgressScreen> createState() => _ProgressScreenState();
}

class _ProgressScreenState extends State<ProgressScreen> {
  Map<String, dynamic>? _data;
  bool _loading = true;
  bool _logging = false;
  final _subjectCtrl = TextEditingController();
  final _topicCtrl = TextEditingController();
  final _durationCtrl = TextEditingController();
  String _activity = 'reading';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final data = await ApiService.get('/progress');
      setState(() { _data = data; _loading = false; });
    } catch (e) {
      setState(() => _loading = false);
    }
  }

  Future<void> _logSession() async {
    if (_subjectCtrl.text.trim().isEmpty || _durationCtrl.text.trim().isEmpty) return;
    setState(() => _logging = true);
    try {
      await ApiService.post('/progress/log', {
        'subject': _subjectCtrl.text.trim(),
        'topic': _topicCtrl.text.trim(),
        'duration': int.tryParse(_durationCtrl.text) ?? 0,
        'activity_type': _activity,
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Session logged!'), backgroundColor: Color(0xFF065F46)));
        _subjectCtrl.clear(); _topicCtrl.clear(); _durationCtrl.clear();
        await _load();
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red));
    } finally {
      setState(() => _logging = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Progress'), leading: IconButton(icon: const Icon(Icons.menu), onPressed: () => Scaffold.of(context).openDrawer())),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: Color(0xFFA855F7)))
          : RefreshIndicator(
              onRefresh: _load,
              child: SingleChildScrollView(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: const EdgeInsets.all(16),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  _buildStats(),
                  const SizedBox(height: 20),
                  _buildWeakTopics(),
                  const SizedBox(height: 20),
                  _buildMastery(),
                  const SizedBox(height: 20),
                  _buildLog(),
                ]),
              ),
            ),
    );
  }

  Widget _buildStats() {
    final sessions = _data?['sessions'] ?? [];
    final totalMinutes = sessions.fold<int>(0, (sum, s) => sum + ((s['duration'] as num?)?.toInt() ?? 0));
    final hours = (totalMinutes / 60).toStringAsFixed(1);
    return Row(children: [
      Expanded(child: _statCard('Study Hours', '${hours}h', const Color(0xFF3B82F6))),
      const SizedBox(width: 10),
      Expanded(child: _statCard('Sessions', sessions.length.toString(), const Color(0xFFA855F7))),
    ]);
  }

  Widget _statCard(String label, String value, Color color) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: const Color(0xFF131629), borderRadius: BorderRadius.circular(12), border: Border.all(color: const Color(0xFF1E2235))),
      child: Column(children: [
        Text(value, style: TextStyle(fontSize: 24, fontWeight: FontWeight.w800, color: color)),
        const SizedBox(height: 4),
        Text(label, style: const TextStyle(fontSize: 12, color: Color(0xFF94A3B8))),
      ]),
    );
  }

  Widget _buildWeakTopics() {
    final weak = _data?['weak_topics'] as List? ?? [];
    if (weak.isEmpty) return const SizedBox();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Row(children: [Icon(Icons.warning_amber, color: Color(0xFFF59E0B), size: 18), SizedBox(width: 6), Text('Weak Topics', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: Colors.white))]),
      const SizedBox(height: 10),
      ...weak.map((w) => Container(
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(color: const Color(0xFF131629), borderRadius: BorderRadius.circular(8), border: Border.all(color: const Color(0xFF1E2235))),
        child: Row(children: [
          Expanded(child: Text(w['topic'] ?? w.toString(), style: const TextStyle(fontSize: 13, color: Color(0xFFCBD5E1)))),
          Container(padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3), decoration: BoxDecoration(color: const Color(0xFF7F1D1D), borderRadius: BorderRadius.circular(12)), child: Text('${w['score'] ?? 'Low'}', style: const TextStyle(fontSize: 11, color: Color(0xFFFCA5A5)))),
        ]),
      )),
    ]);
  }

  Widget _buildMastery() {
    final mastery = _data?['mastery'] as List? ?? [];
    if (mastery.isEmpty) return const SizedBox();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Subject Mastery', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: Colors.white)),
      const SizedBox(height: 10),
      ...mastery.take(10).map((m) {
        final pct = ((m['mastery'] as num?)?.toDouble() ?? 0).clamp(0, 100);
        return Container(
          margin: const EdgeInsets.only(bottom: 10),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
              Text(m['subject'] ?? '', style: const TextStyle(fontSize: 13, color: Color(0xFFCBD5E1))),
              Text('${pct.round()}%', style: const TextStyle(fontSize: 12, color: Color(0xFF94A3B8))),
            ]),
            const SizedBox(height: 4),
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(value: pct / 100, minHeight: 6, backgroundColor: const Color(0xFF1E2235), color: pct > 70 ? const Color(0xFF22C55E) : pct > 40 ? const Color(0xFFF59E0B) : const Color(0xFFEF4444)),
            ),
          ]),
        );
      }),
    ]);
  }

  Widget _buildLog() {
    return Card(child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('Log Study Session', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: Colors.white)),
        const SizedBox(height: 12),
        TextField(controller: _subjectCtrl, decoration: const InputDecoration(labelText: 'Subject', isDense: true)),
        const SizedBox(height: 10),
        TextField(controller: _topicCtrl, decoration: const InputDecoration(labelText: 'Topic', isDense: true)),
        const SizedBox(height: 10),
        Row(children: [
          Expanded(child: TextField(controller: _durationCtrl, decoration: const InputDecoration(labelText: 'Minutes', isDense: true), keyboardType: TextInputType.number)),
          const SizedBox(width: 10),
          Expanded(child: DropdownButtonFormField<String>(value: _activity, decoration: const InputDecoration(labelText: 'Activity', isDense: true), dropdownColor: const Color(0xFF131629), items: const [DropdownMenuItem(value: 'reading', child: Text('Reading')), DropdownMenuItem(value: 'quiz', child: Text('Quiz')), DropdownMenuItem(value: 'flashcard', child: Text('Flashcard')), DropdownMenuItem(value: 'notes', child: Text('Notes'))], onChanged: (v) => _activity = v ?? 'reading')),
        ]),
        const SizedBox(height: 12),
        SizedBox(width: double.infinity, child: ElevatedButton(onPressed: _logging ? null : _logSession, child: Text(_logging ? 'Logging...' : 'Log Session'))),
      ]),
    ));
  }
}

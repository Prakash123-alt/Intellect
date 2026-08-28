import 'package:flutter/material.dart';
import '../services/api_service.dart';

class StudyPlanScreen extends StatefulWidget {
  const StudyPlanScreen({super.key});

  @override
  State<StudyPlanScreen> createState() => _StudyPlanScreenState();
}

class _StudyPlanScreenState extends State<StudyPlanScreen> {
  List<dynamic> _plans = [];
  Map<String, dynamic>? _selectedPlan;
  bool _loading = true;
  bool _creating = false;
  final _subjectCtrl = TextEditingController();
  final _topicsCtrl = TextEditingController();
  final _hoursCtrl = TextEditingController(text: '2');
  final _daysCtrl = TextEditingController(text: '14');

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final data = await ApiService.get('/study-plans');
      setState(() { _plans = data is List ? data : []; _loading = false; });
    } catch (e) {
      setState(() => _loading = false);
    }
  }

  Future<void> _create() async {
    if (_subjectCtrl.text.trim().isEmpty || _topicsCtrl.text.trim().isEmpty) return;
    setState(() => _creating = true);
    try {
      final data = await ApiService.post('/study-plans', {
        'subject': _subjectCtrl.text.trim(),
        'topics': _topicsCtrl.text.trim().split('\n').where((t) => t.trim().isNotEmpty).toList(),
        'daily_hours': double.tryParse(_hoursCtrl.text) ?? 2,
        'days': int.tryParse(_daysCtrl.text) ?? 14,
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Study plan created!'), backgroundColor: Color(0xFF065F46)));
        _subjectCtrl.clear(); _topicsCtrl.clear();
        await _load();
        _view(data['plan_id']);
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red));
    } finally {
      setState(() => _creating = false);
    }
  }

  Future<void> _view(int planId) async {
    try {
      final data = await ApiService.get('/study-plans/$planId');
      setState(() => _selectedPlan = data);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red));
    }
  }

  Future<void> _updateTask(int planId, int taskId, String status) async {
    try {
      await ApiService.post('/study-plans/$planId/task/$taskId', {'status': status});
      await _view(planId);
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_selectedPlan != null ? 'Plan Details' : 'Study Plan'),
        leading: _selectedPlan != null ? IconButton(icon: const Icon(Icons.arrow_back), onPressed: () => setState(() => _selectedPlan = null)) : IconButton(icon: const Icon(Icons.menu), onPressed: () => Scaffold.of(context).openDrawer()),
      ),
      body: _selectedPlan != null ? _buildDetail() : _buildList(),
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
            const Text('Create Study Plan', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: Colors.white)),
            TextField(controller: _subjectCtrl, decoration: const InputDecoration(labelText: 'Subject', isDense: true)),
            const SizedBox(height: 10),
            TextField(controller: _topicsCtrl, decoration: const InputDecoration(labelText: 'Topics (one per line)', isDense: true), maxLines: 4),
            const SizedBox(height: 10),
            Row(children: [
              Expanded(child: TextField(controller: _hoursCtrl, decoration: const InputDecoration(labelText: 'Hours/day', isDense: true), keyboardType: TextInputType.number)),
              const SizedBox(width: 10),
              Expanded(child: TextField(controller: _daysCtrl, decoration: const InputDecoration(labelText: 'Days', isDense: true), keyboardType: TextInputType.number)),
            ]),
            const SizedBox(height: 12),
            SizedBox(width: double.infinity, child: ElevatedButton.icon(onPressed: _creating ? null : _create, icon: _creating ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)) : const Icon(Icons.calendar_month, size: 18), label: Text(_creating ? 'Creating...' : 'Create Plan'))),
          ]),
        )),
        const SizedBox(height: 20),
        if (_plans.isNotEmpty) ...[
          const Text('Your Plans', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: Colors.white)),
          const SizedBox(height: 12),
          ..._plans.map((p) => Card(child: ListTile(
            leading: const Icon(Icons.calendar_month, color: Color(0xFFA855F7)),
            title: Text(p['subject'] ?? 'Plan', style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
            trailing: const Icon(Icons.chevron_right, color: Color(0xFF64748B)),
            onTap: () => _view(p['id']),
          ))),
        ],
      ]),
    );
  }

  Widget _buildDetail() {
    final plan = _selectedPlan!;
    final tasks = plan['tasks'] as List? ?? [];
    final completed = tasks.where((t) => t['status'] == 'completed').length;
    final total = tasks.length;
    final pct = total > 0 ? (completed / total * 100).round() : 0;
    return Column(children: [
      Container(
        padding: const EdgeInsets.all(16),
        color: const Color(0xFF131629),
        child: Row(children: [
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(plan['subject'] ?? '', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: Colors.white)),
            Text('Exam: ${plan['exam_date'] ?? 'N/A'}', style: const TextStyle(fontSize: 12, color: Color(0xFF94A3B8))),
          ])),
          Container(padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6), decoration: BoxDecoration(color: const Color(0xFF1a1040), borderRadius: BorderRadius.circular(20)), child: Text('$pct%', style: const TextStyle(color: Color(0xFFA855F7), fontWeight: FontWeight.w700))),
        ]),
      ),
      LinearProgressIndicator(value: total > 0 ? completed / total : 0, backgroundColor: const Color(0xFF1E2235), color: const Color(0xFFA855F7)),
      Expanded(
        child: ListView.builder(
          padding: const EdgeInsets.all(12),
          itemCount: tasks.length,
          itemBuilder: (ctx, i) {
            final t = tasks[i];
            final isDone = t['status'] == 'completed';
            return Card(child: ListTile(
              leading: Checkbox(value: isDone, onChanged: (v) => _updateTask(plan['id'], t['id'], v == true ? 'completed' : 'not_started'), activeColor: const Color(0xFF7C3AED)),
              title: Text(t['topic_name'] ?? '', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, decoration: isDone ? TextDecoration.lineThrough : null, color: isDone ? const Color(0xFF64748B) : Colors.white)),
              subtitle: Text('${t['task_type'] ?? ''} • ${t['scheduled_date'] ?? ''}', style: const TextStyle(fontSize: 11, color: Color(0xFF64748B))),
            ));
          },
        ),
      ),
    ]);
  }
}

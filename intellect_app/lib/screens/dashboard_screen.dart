import 'package:flutter/material.dart';
import '../services/api_service.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  Future<dynamic>? _future;

  @override
  void initState() {
    super.initState();
    _future = ApiService.get('/dashboard');
  }

  Future<void> _refresh() async {
    setState(() => _future = ApiService.get('/dashboard'));
  }

  Widget _statCard({required String label, required dynamic value, required Color color}) {
    final display = value is double ? value.toStringAsFixed(value.truncateToDouble() == value ? 0 : 1) : value.toString();
    return Container(
      decoration: BoxDecoration(color: const Color(0xFF131629), borderRadius: BorderRadius.circular(12), border: Border.all(color: const Color(0xFF1E2235))),
      padding: const EdgeInsets.symmetric(vertical: 20, horizontal: 12),
      child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
        Text(display, style: TextStyle(fontSize: 28, fontWeight: FontWeight.w800, color: color)),
        const SizedBox(height: 6),
        Text(label, textAlign: TextAlign.center, style: const TextStyle(fontSize: 12, color: Color(0xFF94A3B8))),
      ]),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Dashboard'),
        leading: IconButton(icon: const Icon(Icons.menu), onPressed: () => Scaffold.of(context).openDrawer()),
      ),
      body: FutureBuilder<dynamic>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) return const Center(child: CircularProgressIndicator(color: Color(0xFFA855F7)));
          if (snapshot.hasError) return Center(child: Padding(padding: const EdgeInsets.all(16), child: Text('Error: ${snapshot.error}', style: const TextStyle(color: Colors.white))));
          final data = snapshot.data ?? {};
          final study = data['study_overview'] ?? {};
          return RefreshIndicator(
            onRefresh: _refresh,
            child: SingleChildScrollView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Welcome back! Here\'s your exam preparation overview.', style: TextStyle(color: Color(0xFFCBD5E1), fontSize: 14)),
                  const SizedBox(height: 20),
                  GridView.count(
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    crossAxisCount: 2,
                    childAspectRatio: 1.1,
                    crossAxisSpacing: 12,
                    mainAxisSpacing: 12,
                    children: [
                      _statCard(label: 'Quizzes', value: data['total_quizzes'] ?? 0, color: const Color(0xFFA855F7)),
                      _statCard(label: 'Flashcards', value: data['total_flashcards'] ?? 0, color: const Color(0xFF22C55E)),
                      _statCard(label: 'Study Hours', value: '${data['total_study_hours'] ?? 0}h', color: const Color(0xFF3B82F6)),
                      _statCard(label: 'Notes', value: data['total_notes'] ?? 0, color: const Color(0xFFF59E0B)),
                    ],
                  ),
                  const SizedBox(height: 24),
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(color: const Color(0xFF131629), borderRadius: BorderRadius.circular(12), border: Border.all(color: const Color(0xFF1E2235))),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('Study Plan Overview', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: Colors.white)),
                        const SizedBox(height: 12),
                        Text("Today's Tasks: ${(study['today_tasks'] ?? []).length}", style: const TextStyle(color: Color(0xFFCBD5E1))),
                        Text("Upcoming (3 days): ${(study['upcoming_tasks'] ?? []).length}", style: const TextStyle(color: Color(0xFFCBD5E1))),
                        Text("Readiness: ${study['readiness'] ?? 0}%", style: const TextStyle(color: Color(0xFFCBD5E1))),
                      ],
                    ),
                  ),
                  const SizedBox(height: 20),
                  const Text('Quick Actions', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: Colors.white)),
                  const SizedBox(height: 12),
                  _action(Icons.smart_toy, 'Ask AI any study question'),
                  _action(Icons.style, 'Generate flashcards for any topic'),
                  _action(Icons.quiz, 'Create quizzes to test yourself'),
                  _action(Icons.edit_note, 'Convert text to structured notes'),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _action(IconData icon, String text) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(children: [
        Icon(icon, size: 16, color: const Color(0xFFA855F7)),
        const SizedBox(width: 10),
        Text(text, style: const TextStyle(fontSize: 13, color: Color(0xFFCBD5E1))),
      ]),
    );
  }
}

import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import '../services/api_service.dart';

class AskScreen extends StatefulWidget {
  const AskScreen({super.key});

  @override
  State<AskScreen> createState() => _AskScreenState();
}

class _AskScreenState extends State<AskScreen> {
  final _questionCtrl = TextEditingController();
  final _subjectCtrl = TextEditingController();
  bool _useRag = false;
  String? _answer;
  double? _elapsed;
  bool _loading = false;
  String? _error;

  Future<void> _ask() async {
    if (_questionCtrl.text.trim().isEmpty) return;
    setState(() { _loading = true; _answer = null; _error = null; _elapsed = null; });
    final sw = Stopwatch()..start();
    try {
      final data = await ApiService.post('/ask', {
        'question': _questionCtrl.text.trim(),
        'subject': _subjectCtrl.text.trim(),
        'use_rag': _useRag,
      });
      sw.stop();
      setState(() {
        _answer = data['answer'];
        _elapsed = (data['response_time'] as num?)?.toDouble() ?? (sw.elapsedMilliseconds / 1000.0);
      });
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Ask AI'), leading: IconButton(icon: const Icon(Icons.menu), onPressed: () => Scaffold.of(context).openDrawer())),
      body: Column(children: [
        Container(
          padding: const EdgeInsets.all(16),
          color: const Color(0xFF131629),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            TextField(controller: _subjectCtrl, decoration: const InputDecoration(labelText: 'Subject (optional)', isDense: true)),
            const SizedBox(height: 10),
            TextField(controller: _questionCtrl, decoration: const InputDecoration(labelText: 'Ask any question...', isDense: true), maxLines: 3, textInputAction: TextInputAction.done),
            const SizedBox(height: 8),
            Row(children: [
              SizedBox(height: 24, width: 24, child: Checkbox(value: _useRag, onChanged: (v) => setState(() => _useRag = v ?? false), materialTapTargetSize: MaterialTapTargetSize.shrinkWrap)),
              const SizedBox(width: 6),
              const Text('Use knowledge base', style: TextStyle(fontSize: 13, color: Color(0xFF94A3B8))),
              const Spacer(),
              ElevatedButton.icon(
                onPressed: _loading ? null : _ask,
                icon: _loading ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)) : const Icon(Icons.send, size: 16),
                label: Text(_loading ? 'Thinking...' : 'Ask'),
              ),
            ]),
          ]),
        ),
        Expanded(child: _buildBody()),
      ]),
    );
  }

  Widget _buildBody() {
    if (_loading) return const Center(child: Column(mainAxisSize: MainAxisSize.min, children: [CircularProgressIndicator(color: Color(0xFFA855F7)), SizedBox(height: 12), Text('Generating answer...', style: TextStyle(color: Color(0xFF94A3B8)))]));
    if (_error != null) return Center(child: Padding(padding: const EdgeInsets.all(16), child: Text(_error!, style: const TextStyle(color: Colors.redAccent))));
    if (_answer != null) {
      return SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          if (_elapsed != null) Container(padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4), margin: const EdgeInsets.only(bottom: 12), decoration: BoxDecoration(color: const Color(0xFF131629), borderRadius: BorderRadius.circular(6)), child: Text('⏱ ${_elapsed!.toStringAsFixed(2)}s', style: const TextStyle(fontSize: 12, color: Color(0xFF64748B)))),
          MarkdownBody(
            data: _answer!,
            styleSheet: MarkdownStyleSheet(
              p: const TextStyle(color: Color(0xFFCBD5E1), fontSize: 14, height: 1.7),
              h1: const TextStyle(color: Color(0xFFE2E8F0), fontSize: 20, fontWeight: FontWeight.w700),
              h2: const TextStyle(color: Color(0xFFE2E8F0), fontSize: 18, fontWeight: FontWeight.w700),
              h3: const TextStyle(color: Color(0xFFE2E8F0), fontSize: 16, fontWeight: FontWeight.w700),
              strong: const TextStyle(color: Color(0xFFE2E8F0), fontWeight: FontWeight.w700),
              code: TextStyle(color: const Color(0xFFA855F7), backgroundColor: const Color(0xFF0B0D1A), fontSize: 13),
            ),
          ),
        ]),
      );
    }
    return const Center(child: Column(mainAxisSize: MainAxisSize.min, children: [Icon(Icons.smart_toy, size: 48, color: Color(0xFF475569)), SizedBox(height: 12), Text('Ask any question to get started', style: TextStyle(color: Color(0xFF64748B)))]));
  }
}

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../services/api_service.dart';

class VisualizeScreen extends StatefulWidget {
  const VisualizeScreen({super.key});

  @override
  State<VisualizeScreen> createState() => _VisualizeScreenState();
}

class _VisualizeScreenState extends State<VisualizeScreen> {
  final _contentCtrl = TextEditingController();
  String _diagramType = 'mindmap';
  String? _mermaidCode;
  bool _loading = false;
  String? _error;

  Future<void> _generate() async {
    if (_contentCtrl.text.trim().isEmpty) return;
    setState(() { _loading = true; _mermaidCode = null; _error = null; });
    try {
      final data = await ApiService.post('/visualize', {
        'content': _contentCtrl.text.trim(),
        'diagram_type': _diagramType,
      });
      setState(() => _mermaidCode = data['mermaid_code']);
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      setState(() => _loading = false);
    }
  }

  void _copy() {
    if (_mermaidCode != null) {
      Clipboard.setData(ClipboardData(text: _mermaidCode!));
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Mermaid code copied!'), backgroundColor: Color(0xFF065F46)));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Visual Learning'), leading: IconButton(icon: const Icon(Icons.menu), onPressed: () => Scaffold.of(context).openDrawer())),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Card(child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('Generate Diagram', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: Colors.white)),
              const Text('Paste study text to generate a Mermaid diagram', style: TextStyle(fontSize: 12, color: Color(0xFF64748B))),
              const SizedBox(height: 12),
              TextField(controller: _contentCtrl, decoration: const InputDecoration(labelText: 'Content to visualize', isDense: true, hintText: 'Paste explanation or notes...'), maxLines: 5),
              const SizedBox(height: 10),
              DropdownButtonFormField<String>(
                value: _diagramType,
                decoration: const InputDecoration(labelText: 'Diagram Type', isDense: true),
                dropdownColor: const Color(0xFF131629),
                items: const [
                  DropdownMenuItem(value: 'mindmap', child: Text('Mind Map')),
                  DropdownMenuItem(value: 'flowchart', child: Text('Flowchart')),
                  DropdownMenuItem(value: 'concept', child: Text('Concept Map')),
                  DropdownMenuItem(value: 'process', child: Text('Process Diagram')),
                ],
                onChanged: (v) => _diagramType = v ?? 'mindmap',
              ),
              const SizedBox(height: 12),
              SizedBox(width: double.infinity, child: ElevatedButton.icon(
                onPressed: _loading ? null : _generate,
                icon: _loading ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)) : const Icon(Icons.auto_awesome, size: 18),
                label: Text(_loading ? 'Generating...' : 'Generate Diagram'),
              )),
            ]),
          )),
          if (_error != null) ...[
            const SizedBox(height: 16),
            Container(padding: const EdgeInsets.all(12), decoration: BoxDecoration(color: const Color(0xFF7F1D1D), borderRadius: BorderRadius.circular(8)), child: Text(_error!, style: const TextStyle(color: Color(0xFFFCA5A5), fontSize: 13))),
          ],
          if (_mermaidCode != null) ...[
            const SizedBox(height: 20),
            Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
              const Text('Mermaid Code', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: Colors.white)),
              IconButton(icon: const Icon(Icons.copy, size: 20, color: Color(0xFFA855F7)), onPressed: _copy),
            ]),
            const SizedBox(height: 8),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(color: const Color(0xFF0B0D1A), borderRadius: BorderRadius.circular(8), border: Border.all(color: const Color(0xFF1E2235))),
              child: SelectableText(_mermaidCode!, style: const TextStyle(fontFamily: 'monospace', fontSize: 13, color: Color(0xFFCBD5E1), height: 1.5)),
            ),
            const SizedBox(height: 12),
            const Text('💡 Copy this and paste in mermaid.live to view the diagram', style: TextStyle(fontSize: 12, color: Color(0xFF64748B))),
          ],
        ]),
      ),
    );
  }
}

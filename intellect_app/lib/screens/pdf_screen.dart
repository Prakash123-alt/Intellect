import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import '../services/api_service.dart';

class PdfScreen extends StatefulWidget {
  const PdfScreen({super.key});

  @override
  State<PdfScreen> createState() => _PdfScreenState();
}

class _PdfScreenState extends State<PdfScreen> {
  List<dynamic> _pdfs = [];
  bool _loading = true;
  int? _selectedPdfId;
  final _questionCtrl = TextEditingController();
  String? _answer;
  bool _asking = false;

  @override
  void initState() {
    super.initState();
    _loadPdfs();
  }

  Future<void> _loadPdfs() async {
    try {
      final data = await ApiService.get('/pdfs');
      setState(() { _pdfs = data is List ? data : []; _loading = false; });
    } catch (e) {
      setState(() => _loading = false);
    }
  }

  Future<void> _askPdf() async {
    if (_selectedPdfId == null || _questionCtrl.text.trim().isEmpty) return;
    setState(() { _asking = true; _answer = null; });
    try {
      final data = await ApiService.post('/pdfs/$_selectedPdfId/ask', {'question': _questionCtrl.text.trim()});
      setState(() => _answer = data['answer']);
    } catch (e) {
      setState(() => _answer = 'Error: $e');
    } finally {
      setState(() => _asking = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('PDF Study'), leading: IconButton(icon: const Icon(Icons.menu), onPressed: () => Scaffold.of(context).openDrawer())),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: Color(0xFFA855F7)))
          : _pdfs.isEmpty
              ? const Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
                  Icon(Icons.picture_as_pdf, size: 48, color: Color(0xFF475569)),
                  SizedBox(height: 12),
                  Text('No PDFs uploaded yet', style: TextStyle(color: Color(0xFF64748B))),
                  Text('Upload PDFs from the web app to study here', style: TextStyle(color: Color(0xFF475569), fontSize: 12)),
                ]))
              : Column(children: [
                  Container(
                    padding: const EdgeInsets.all(12),
                    color: const Color(0xFF131629),
                    child: Column(children: [
                      DropdownButtonFormField<int>(
                        value: _selectedPdfId,
                        decoration: const InputDecoration(labelText: 'Select PDF', isDense: true),
                        dropdownColor: const Color(0xFF131629),
                        items: _pdfs.map<DropdownMenuItem<int>>((p) => DropdownMenuItem(value: p['id'], child: Text(p['original_name'] ?? 'PDF', overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 13)))).toList(),
                        onChanged: (v) => setState(() => _selectedPdfId = v),
                      ),
                      const SizedBox(height: 10),
                      Row(children: [
                        Expanded(child: TextField(controller: _questionCtrl, decoration: const InputDecoration(labelText: 'Ask about this PDF...', isDense: true))),
                        const SizedBox(width: 8),
                        ElevatedButton(onPressed: _asking ? null : _askPdf, child: _asking ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)) : const Icon(Icons.send, size: 18)),
                      ]),
                    ]),
                  ),
                  Expanded(
                    child: _answer != null
                        ? SingleChildScrollView(
                            padding: const EdgeInsets.all(16),
                            child: MarkdownBody(data: _answer!, styleSheet: MarkdownStyleSheet(p: const TextStyle(color: Color(0xFFCBD5E1), fontSize: 14, height: 1.7))),
                          )
                        : ListView.builder(
                            padding: const EdgeInsets.all(12),
                            itemCount: _pdfs.length,
                            itemBuilder: (ctx, i) {
                              final p = _pdfs[i];
                              return Card(child: ListTile(
                                leading: const Icon(Icons.picture_as_pdf, color: Color(0xFFA855F7)),
                                title: Text(p['original_name'] ?? '', style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
                                subtitle: Text('${p['page_count'] ?? 0} pages', style: const TextStyle(fontSize: 12, color: Color(0xFF64748B))),
                                onTap: () => setState(() => _selectedPdfId = p['id']),
                              ));
                            },
                          ),
                  ),
                ]),
    );
  }
}

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'dart:convert';
import 'package:http/http.dart' as http;

void main() {
  runApp(const IntellectApp());
}

const Color kBg = Color(0xFF0B0D1A);
const Color kCard = Color(0xFF131629);
const Color kBorder = Color(0xFF1E2235);
const Color kPurple = Color(0xFF7C3AED);
const Color kPurpleLight = Color(0xFFA855F7);
const Color kText = Color(0xFFE2E8F0);
const Color kSubText = Color(0xFF94A3B8);
const Color kMuted = Color(0xFF64748B);
const String groqApiKey = 'YOUR_GROQ_API_KEY_HERE';

class IntellectApp extends StatelessWidget {
  const IntellectApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Intellect AI',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        scaffoldBackgroundColor: kBg,
        colorScheme: const ColorScheme.dark(primary: kPurple),
      ),
      home: const HomePage(),
    );
  }
}

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  final TextEditingController _controller = TextEditingController();
  String _answer = '';
  bool _isLoading = false;

  final List<String> _suggestions = [
    'Deep learning ethics',
    'Quantum physics basics',
    'Future of SaaS',
    'Abstract algebra',
  ];

  Future<void> _askQuestion(String question) async {
    if (question.trim().isEmpty) return;
    setState(() { _isLoading = true; _answer = ''; });
    try {
      final response = await http.post(
        Uri.parse('https://api.groq.com/openai/v1/chat/completions'),
        headers: {
          'Authorization': 'Bearer $groqApiKey',
          'Content-Type': 'application/json',
        },
        body: jsonEncode({
          'model': 'llama-3.1-8b-instant',
          'messages': [{'role': 'user', 'content': question}],
        }),
      );
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        setState(() { _answer = data['choices'][0]['message']['content']; });
      } else {
        setState(() { _answer = 'Error: ${response.statusCode}. Please try again.'; });
      }
    } catch (e) {
      setState(() { _answer = 'Network error. Please check your connection.'; });
    } finally {
      setState(() { _isLoading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            _buildNavbar(),
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const SizedBox(height: 36),
                    _buildHero(),
                    const SizedBox(height: 24),
                    _buildInputCard(),
                    const SizedBox(height: 16),
                    _buildSuggestions(),
                    const SizedBox(height: 24),
                    if (_isLoading) _buildLoading(),
                    if (_answer.isNotEmpty && !_isLoading) _buildAnswerSection(),
                    const SizedBox(height: 32),
                    _buildFeatureCards(),
                    const SizedBox(height: 32),
                    _buildFooter(),
                    const SizedBox(height: 24),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildNavbar() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: kBorder)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          const Row(
            children: [
              Text('âœ¦', style: TextStyle(color: kPurpleLight, fontSize: 18, fontWeight: FontWeight.bold)),
              SizedBox(width: 8),
              Text('Intellect', style: TextStyle(color: kText, fontSize: 18, fontWeight: FontWeight.w700)),
            ],
          ),
          Container(
            width: 36, height: 36,
            decoration: BoxDecoration(
              border: Border.all(color: kBorder),
              borderRadius: BorderRadius.circular(18),
            ),
            child: const Icon(Icons.person_outline, color: kSubText, size: 18),
          ),
        ],
      ),
    );
  }

  Widget _buildHero() {
    return const Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('How can I help you?',
          style: TextStyle(color: kText, fontSize: 26, fontWeight: FontWeight.w800)),
        SizedBox(height: 8),
        Text('Enter your question below to start an intellectual journey.',
          style: TextStyle(color: kSubText, fontSize: 14)),
      ],
    );
  }

  Widget _buildInputCard() {
    return Container(
      decoration: BoxDecoration(
        color: kCard,
        border: Border.all(color: kBorder),
        borderRadius: BorderRadius.circular(16),
      ),
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          TextField(
            controller: _controller,
            maxLines: 4,
            style: const TextStyle(color: kText, fontSize: 15),
            decoration: const InputDecoration(
              hintText: 'Ask anything...',
              hintStyle: TextStyle(color: kMuted),
              border: InputBorder.none,
            ),
          ),
          const SizedBox(height: 12),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Row(
                children: [
                  Icon(Icons.attach_file, color: kMuted, size: 20),
                  SizedBox(width: 16),
                  Icon(Icons.mic_none, color: kMuted, size: 20),
                ],
              ),
              ElevatedButton.icon(
                onPressed: _isLoading ? null : () => _askQuestion(_controller.text),
                icon: const Icon(Icons.arrow_forward, size: 16),
                label: const Text('Ask', style: TextStyle(fontWeight: FontWeight.w600)),
                style: ElevatedButton.styleFrom(
                  backgroundColor: kPurple,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(50)),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildSuggestions() {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: _suggestions.map((s) => GestureDetector(
        onTap: () {
          _controller.text = s;
          _askQuestion(s);
        },
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          decoration: BoxDecoration(
            color: kCard,
            border: Border.all(color: kBorder),
            borderRadius: BorderRadius.circular(50),
          ),
          child: Text(s, style: const TextStyle(color: kSubText, fontSize: 13)),
        ),
      )).toList(),
    );
  }

  Widget _buildLoading() {
    return const Center(
      child: Padding(
        padding: EdgeInsets.all(24),
        child: CircularProgressIndicator(color: kPurple),
      ),
    );
  }

  Widget _buildAnswerSection() {
    return Column(
      children: [
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: const Color(0xFF2D1F5E),
            borderRadius: BorderRadius.circular(16),
          ),
          child: const Text(
            'Your recent inquiry has been processed by our neural core.',
            style: TextStyle(color: Color(0xFFC4B5FD), fontSize: 14),
          ),
        ),
        const SizedBox(height: 12),
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: kCard,
            border: Border.all(color: kBorder),
            borderRadius: BorderRadius.circular(16),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    width: 40, height: 40,
                    decoration: BoxDecoration(
                      color: kPurple,
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: const Center(child: Text('âœ¦', style: TextStyle(color: Colors.white, fontSize: 16))),
                  ),
                  const SizedBox(width: 12),
                  const Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Intellect Intelligence', style: TextStyle(color: kText, fontWeight: FontWeight.w700, fontSize: 14)),
                      Text('RESPONSE GENERATED', style: TextStyle(color: kMuted, fontSize: 10, letterSpacing: 0.8)),
                    ],
                  ),
                ],
              ),
              const SizedBox(height: 14),
              Text(_answer, style: const TextStyle(color: Color(0xFFCBD5E1), fontSize: 14, height: 1.7)),
              const SizedBox(height: 14),
              const Divider(color: kBorder),
              const SizedBox(height: 8),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.thumb_up_outlined, size: 16, color: kMuted),
                      const SizedBox(width: 4),
                      const Text('Helpful', style: TextStyle(color: kMuted, fontSize: 13)),
                      const SizedBox(width: 12),
                      const Icon(Icons.thumb_down_outlined, size: 16, color: kMuted),
                    ],
                  ),
                  Row(
                    children: [
                      GestureDetector(
                        onTap: () {
                          Clipboard.setData(ClipboardData(text: _answer));
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(content: Text('Copied!'), duration: Duration(seconds: 1)),
                          );
                        },
                        child: const Icon(Icons.copy_outlined, size: 16, color: kMuted),
                      ),
                      const SizedBox(width: 12),
                      const Icon(Icons.share_outlined, size: 16, color: kMuted),
                    ],
                  ),
                ],
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildFeatureCards() {
    return Column(
      children: [
        _featureCard('âš™ï¸', 'Neural Synthesis',
          'Leverage state-of-the-art transformer models to synthesize complex information into digestible insights.'),
        const SizedBox(height: 16),
        _featureCard('â–¶_', 'Precision Logic',
          'Advanced reasoning capabilities ensure that every response is grounded in logical consistency and factual accuracy.'),
      ],
    );
  }

  Widget _featureCard(String icon, String title, String desc) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: kCard,
        border: Border.all(color: kBorder),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(icon, style: const TextStyle(fontSize: 22, color: kPurpleLight)),
          const SizedBox(height: 10),
          Text(title, style: const TextStyle(color: kText, fontSize: 16, fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          Text(desc, style: const TextStyle(color: kMuted, fontSize: 13, height: 1.6)),
        ],
      ),
    );
  }

  Widget _buildFooter() {
    return Column(
      children: [
        const Divider(color: kBorder),
        const SizedBox(height: 16),
        const Text('Â© 2024 Intellect AI. Powered by Magic.',
          style: TextStyle(color: kMuted, fontSize: 13)),
        const SizedBox(height: 8),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: ['Privacy', 'Terms', 'Support'].map((t) =>
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 10),
              child: Text(t, style: const TextStyle(color: kMuted, fontSize: 13)),
            )
          ).toList(),
        ),
      ],
    );
  }
}

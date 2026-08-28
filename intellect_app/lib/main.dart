import 'package:flutter/material.dart';
import 'screens/dashboard_screen.dart';
import 'screens/ask_screen.dart';
import 'screens/flashcards_screen.dart';
import 'screens/quiz_screen.dart';
import 'screens/notes_screen.dart';
import 'screens/youtube_screen.dart';
import 'screens/pdf_screen.dart';
import 'screens/study_plan_screen.dart';
import 'screens/progress_screen.dart';
import 'screens/visualize_screen.dart';

void main() {
  runApp(const IntellectApp());
}

class IntellectApp extends StatelessWidget {
  const IntellectApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Intellect AI',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF7C3AED),
          brightness: Brightness.dark,
          surface: const Color(0xFF0B0D1A),
        ),
        useMaterial3: true,
        scaffoldBackgroundColor: const Color(0xFF0B0D1A),
        appBarTheme: const AppBarTheme(backgroundColor: Color(0xFF0B0D1A), surfaceTintColor: Colors.transparent, elevation: 0),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: const Color(0xFF0B0D1A),
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: Color(0xFF1E2235))),
          enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: Color(0xFF1E2235))),
          focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: Color(0xFF7C3AED))),
          labelStyle: const TextStyle(color: Color(0xFF94A3B8)),
          hintStyle: const TextStyle(color: Color(0xFF475569)),
        ),
        elevatedButtonTheme: ElevatedButtonThemeData(
          style: ElevatedButton.styleFrom(
            backgroundColor: const Color(0xFF7C3AED),
            foregroundColor: Colors.white,
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
          ),
        ),
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
  int _selectedIndex = 0;

  final _screens = const [
    DashboardScreen(),
    AskScreen(),
    FlashcardsScreen(),
    QuizScreen(),
    NotesScreen(),
  ];

  final _drawerItems = const [
    {'icon': Icons.dashboard, 'label': 'Dashboard'},
    {'icon': Icons.smart_toy, 'label': 'Ask AI'},
    {'icon': Icons.style, 'label': 'Flashcards'},
    {'icon': Icons.quiz, 'label': 'Quiz'},
    {'icon': Icons.edit_note, 'label': 'Notes'},
    {'icon': Icons.video_library, 'label': 'YouTube'},
    {'icon': Icons.picture_as_pdf, 'label': 'PDF Study'},
    {'icon': Icons.calendar_month, 'label': 'Study Plan'},
    {'icon': Icons.trending_up, 'label': 'Progress'},
    {'icon': Icons.account_tree, 'label': 'Visualize'},
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: _screens[_selectedIndex],
      drawer: Drawer(
        backgroundColor: const Color(0xFF0D0F1E),
        child: SafeArea(
          child: Column(
            children: [
              Container(
                padding: const EdgeInsets.all(20),
                decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: Color(0xFF1E2235)))),
                child: const Row(children: [
                  Icon(Icons.auto_awesome, color: Color(0xFFA855F7), size: 28),
                  SizedBox(width: 10),
                  Text('Intellect AI', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: Colors.white)),
                ]),
              ),
              Expanded(
                child: ListView.builder(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  itemCount: _drawerItems.length,
                  itemBuilder: (context, index) {
                    final item = _drawerItems[index];
                    final selected = index == _selectedIndex;
                    return ListTile(
                      dense: true,
                      leading: Icon(item['icon'] as IconData, color: selected ? const Color(0xFFA855F7) : const Color(0xFF94A3B8), size: 20),
                      title: Text(item['label'] as String, style: TextStyle(color: selected ? const Color(0xFFA855F7) : const Color(0xFF94A3B8), fontSize: 14, fontWeight: selected ? FontWeight.w600 : FontWeight.w500)),
                      onTap: () {
                        if (item['label'] == 'YouTube') {
                          Navigator.push(context, MaterialPageRoute(builder: (_) => const YouTubeScreen()));
                        } else if (item['label'] == 'PDF Study') {
                          Navigator.push(context, MaterialPageRoute(builder: (_) => const PdfScreen()));
                        } else if (item['label'] == 'Study Plan') {
                          Navigator.push(context, MaterialPageRoute(builder: (_) => const StudyPlanScreen()));
                        } else if (item['label'] == 'Progress') {
                          Navigator.push(context, MaterialPageRoute(builder: (_) => const ProgressScreen()));
                        } else if (item['label'] == 'Visualize') {
                          Navigator.push(context, MaterialPageRoute(builder: (_) => const VisualizeScreen()));
                        } else {
                          setState(() => _selectedIndex = index);
                        }
                        Navigator.pop(context);
                      },
                    );
                  },
                ),
              ),
            ],
          ),
        ),
      ),
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _selectedIndex,
        onTap: (i) => setState(() => _selectedIndex = i),
        type: BottomNavigationBarType.fixed,
        backgroundColor: const Color(0xFF0D0F1E),
        selectedItemColor: const Color(0xFFA855F7),
        unselectedItemColor: const Color(0xFF64748B),
        items: const [
          BottomNavigationBarItem(icon: Icon(Icons.dashboard), label: 'Home'),
          BottomNavigationBarItem(icon: Icon(Icons.smart_toy), label: 'Ask AI'),
          BottomNavigationBarItem(icon: Icon(Icons.style), label: 'Cards'),
          BottomNavigationBarItem(icon: Icon(Icons.quiz), label: 'Quiz'),
          BottomNavigationBarItem(icon: Icon(Icons.edit_note), label: 'Notes'),
        ],
      ),
    );
  }
}

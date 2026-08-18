from flask import Flask, render_template, request
from groq import Groq
import os
import re
import markdown
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

@app.route('/', methods=['GET', 'POST'])
def index():
    answer = ""
    if request.method == 'POST':
        user_input = request.form['question']
        response = client.chat.completions.create(
            model="qwen/qwen3.6-27b",
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Give clear, concise answers. Do not include any thinking or reasoning tags."},
                {"role": "user", "content": user_input}
            ]
        )
        raw = response.choices[0].message.content
        raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
        answer = markdown.markdown(raw, extensions=['tables', 'fenced_code'])
    return render_template('index.html', answer=answer)

if __name__ == '__main__':
    app.run(debug=True)

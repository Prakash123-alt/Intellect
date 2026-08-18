from flask import Flask, render_template, request
from groq import Groq
import os
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
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": user_input}]
        )
        answer = response.choices[0].message.content
    return render_template('index.html', answer=answer)

if __name__ == '__main__':
    app.run(debug=True)

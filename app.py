from flask import Flask, render_template, Response

app = Flask(__name__)

# 1. मुख्य पब्लिक वेबसाइट (आपकी पुरानी साइट)
@app.route('/')
def home():
    return render_template('index.html')

# 2. एक्सोटेल का अलग वेबहुक
@app.route('/voice-webhook', methods=['GET', 'POST'])
def voice_webhook():
    xml_response = """<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Say language="hi-IN">ध्रुव एकेडमी में आपका स्वागत है।</Say>
    </Response>"""
    return Response(xml_response, mimetype='text/xml')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

import os
from flask import Flask, render_template, Response

# सही पाथ सेट करें ताकि Flask को templates और static फोल्डर मिल जाएं
template_dir = os.path.abspath('templates')
static_dir = os.path.abspath('static')

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

# 1. मुख्य पब्लिक वेबसाइट / होमपेज
@app.route('/')
def home():
    return render_template('index.html')

# 2. एक्सोटेल का वेबहुक रूट
@app.route('/voice-webhook', methods=['GET', 'POST'])
def voice_webhook():
    xml_response = """<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Say language="hi-IN">ध्रुव एकेडमी में आपका स्वागत है।</Say>
    </Response>"""
    return Response(xml_response, mimetype='text/xml')

# आपके बाकी 13 मॉड्यूल्स के रूट्स यहाँ नीचे डिफाइन रहेंगे...

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

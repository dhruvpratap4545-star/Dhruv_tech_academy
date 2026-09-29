import os
from flask import Flask, render_template, Response, request, jsonify

# सही पाथ सेट करें ताकि Flask को templates और static फोल्डर मिल जाएं
template_dir = os.path.abspath('templates')
static_dir = os.path.abspath('static')

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

# 1. मुख्य पब्लिक वेबसाइट / होमपेज
@app.route('/')
def home():
    return render_template('index.html')

# 2. एक्सोटेल का वेबहुक रूट (सुरक्षित और यथावत)
@app.route('/voice-webhook', methods=['GET', 'POST'])
def voice_webhook():
    xml_response = """<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Say language="hi-IN">ध्रुव एकेडमी में आपका स्वागत है।</Say>
    </Response>"""
    return Response(xml_response, mimetype='text/xml')

# 3. सभी मॉड्यूल्स के सटीक राउट्स (templates फोल्डर की वास्तविक फाइलों के अनुसार)
@app.route('/ai-core')
@app.route('/ai-core.html')
def ai_core():
    return render_template('ai-core.html')

@app.route('/ai-auto-healing')
@app.route('/ai-auto-healing.html')
def ai_auto_healing():
    return render_template('ai-auto-healing.html')

@app.route('/digital-library')
@app.route('/digital-library.html')
def digital_library():
    return render_template('digital-library.html')

@app.route('/kids-zone')
@app.route('/kids-zone.html')
def kids_zone():
    return render_template('kids-zone.html')

@app.route('/spoken-english')
@app.route('/spoken-english.html')
def spoken_english():
    return render_template('spoken-english.html')

@app.route('/face-swap-social')
@app.route('/face-swap-social.html')
def face_swap_social():
    return render_template('face-swap-social.html')

@app.route('/central-wallet')
@app.route('/central-wallet.html')
def central_wallet():
    return render_template('central-wallet.html')

@app.route('/competition-solver')
@app.route('/competition-solver.html')
def competition_solver():
    return render_template('competition-solver.html')

@app.route('/coaching-hub')
@app.route('/coaching-hub.html')
def coaching_hub():
    return render_template('coaching-hub.html')

# लीगल एआई असिस्टेंट (फाइल नाम: legal-ai.html के अनुसार)
@app.route('/legal-hub')
@app.route('/legal-hub.html')
@app.route('/legal-ai-assistant')
def legal_ai_assistant():
    return render_template('legal-ai.html')

# जीरो ट्रस्ट मोबाइल शील्ड / सुरक्षा मॉड्यूल
@app.route('/shield-router')
@app.route('/zero-trust-shield')
@app.route('/shield.html')
def zero_trust_shield():
    return render_template('shield.html')

@app.route('/admin/super-master-panel')
def super_master_panel():
    return render_template('admin_login.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

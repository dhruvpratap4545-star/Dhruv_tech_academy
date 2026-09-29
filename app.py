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

# 2. एक्सोटेल का वेबहुक रूट
@app.route('/voice-webhook', methods=['GET', 'POST'])
def voice_webhook():
    xml_response = """<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Say language="hi-IN">ध्रुव एकेडमी में आपका स्वागत है।</Say>
    </Response>"""
    return Response(xml_response, mimetype='text/xml')

# 3. सभी 12 मॉड्यूल्स के सुरक्षित रूट्स (Flask Routes for 12 Modules)
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

@app.route('/live-guard-ai')
@app.route('/live-guard-ai.html')
def live_guard_ai():
    return render_template('live-guard-ai.html')

@app.route('/dhruv-mitra')
@app.route('/dhruv-mitra.html')
def dhruv_mitra():
    return render_template('dhruv-mitra.html')

@app.route('/admin/super-master-panel')
def super_master_panel():
    return render_template('super-master-panel.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

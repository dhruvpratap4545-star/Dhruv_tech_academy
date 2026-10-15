import os
import time
import google.generativeai as genai
from flask import Flask, render_template, Response, request, jsonify

# सही पाथ सेट करें ताकि Flask को templates और static फोल्डर मिल जाएं
template_dir = os.path.abspath('templates')
static_dir = os.path.abspath('static')

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

# ==========================================
# 1. जेमिनी एआई सुरक्षित एपीआई और मल्टी-मॉडल लूप सेटअप
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("चेतावनी: GEMINI_API_KEY एनवायरमेंट में सेट नहीं है!")

def generate_gemini_response_safely(prompt_text):
    # आपके निर्देशानुसार 1.5, 2.5 और 3.5 वर्ज़न्स का फॉलबैक लूप
    model_volumes = [
        "gemini-1.5-pro",   
        "gemini-2.5-flash", 
        "gemini-3.5-pro"    
    ]
    
    max_retries = 3  
    for attempt in range(max_retries):
        for model_name in model_volumes:
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt_text)
                
                if response and response.text:
                    return response.text
            except Exception as e:
                print(f"मॉडल {model_name} पर एरर आया: {e}")
                continue 
        
        # यदि सभी मॉडल्स व्यस्त हों, तो 30 सेकंड का इंतज़ार करके ऑटो-रीट्राई करेगा
        print(f"सिस्टम व्यस्त है। अगले प्रयास से पहले 30 सेकंड का इंतज़ार किया जा रहा है... (प्रयास {attempt+1}/{max_retries})")
        time.sleep(30)
        
    return "माफ कीजिए, वर्तमान में सभी एआई सर्वर अत्यधिक व्यस्त हैं। कृपया 30 सेकंड बाद पुनः प्रयास करें।"


# ==========================================
# 2. मुख्य पब्लिक वेबसाइट और एक्सोटेल वेबहुक रूट्स
# ==========================================
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/voice-webhook', methods=['GET', 'POST'])
def voice_webhook():
    xml_response = """<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Say language="hi-IN">ध्रुव एकेडमी में आपका स्वागत है।</Say>
    </Response>"""
    return Response(xml_response, mimetype='text/xml')


# ==========================================
# 3. सभी 12 मॉड्यूल्स के सुरक्षित रूट्स (सटीक पाथ के साथ)
# ==========================================
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

# लीगल एआई असिस्टेंट (सटीक फाइल नाम: legal-ai.html)
@app.route('/legal-ai')
@app.route('/legal-ai.html')
@app.route('/legal-hub')
@app.route('/legal-hub.html')
def legal_ai_assistant():
    return render_template('legal-ai.html')

# जीरो ट्रस्ट मोबाइल शील्ड (सटीक फाइल नाम: mobile-shield.html)
@app.route('/mobile-shield')
@app.route('/mobile-shield.html')
@app.route('/shield')
@app.route('/shield.html')
def zero_trust_shield():
    return render_template('mobile-shield.html')

@app.route('/admin/super-master-panel')
def super_master_panel():
    return render_template('admin_login.html')


# ==========================================
# 4. एआई टेस्टिंग या एपीआई कॉलिंग के लिए सुरक्षित राउट
# ==========================================
@app.route('/api/ask-gemini', methods=['POST'])
def api_ask_gemini():
    user_prompt = request.json.get('prompt', 'नमस्ते') if request.is_json else request.form.get('prompt', 'नमस्ते')
    ai_answer = generate_gemini_response_safely(user_prompt)
    return jsonify({"status": "success", "response": ai_answer})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

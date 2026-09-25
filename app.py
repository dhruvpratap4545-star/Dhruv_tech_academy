from flask import Flask, render_template, request
from twilio.twiml.voice_response import VoiceResponse

app = Flask(__name__)

@app.route('/')
def home():
    """यह मुख्य होमपेज (index.html) को रेंडर करेगा"""
    return render_template('index.html')

@app.route('/voice-webhook', methods=['POST', 'GET'])
def voice_webhook():
    """यह तब काम करेगा जब कोई एआई कॉलिंग या वेबहुक ट्रिगर होगा"""
    response = VoiceResponse()
    
    # बिल्कुल प्राकृतिक और स्पष्ट हिंदी वॉइस संदेश
    ai_message = "नमस्ते! ध्रुव एकेडमी में आपका स्वागत है। आपके प्रतियोगी परीक्षाओं और स्मार्ट लर्निंग के नए मॉड्यूल्स अब लाइव हो चुके हैं।"
    
    # Twilio की नेचुरल हिंदी वॉइस (Aditi) का उपयोग
    response.say(ai_message, voice='Polly.Aditi', language='hi-IN')
    
    return str(response), 200, {'Content-Type': 'application/xml'}

if __name__ == '__main__':
    # Render और लोकल दोनों के लिए पोर्ट कॉन्फ़िगरेशन
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

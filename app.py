from flask import Flask, render_template, request
from twilio.twiml.voice_response import VoiceResponse
import os

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/voice-webhook', methods=['GET', 'POST'])
def voice_webhook():
    try:
        response = VoiceResponse()
        ai_message = "नमस्ते! ध्रुव एकेडमी में आपका स्वागत है। आपके प्रतियोगी परीक्षाओं और स्मार्ट लर्निंग के नए मॉड्यूल्स अब लाइव हो चुके हैं।"
        response.say(ai_message, voice='Polly.Aditi', language='hi-IN')
        return str(response), 200, {'Content-Type': 'application/xml'}
    except Exception as e:
        return f"<Response><Say>Error occurred: {str(e)}</Say></Response>", 200, {'Content-Type': 'application/xml'}

# यदि कोई कस्टम 404 एरर हैंडलर ऊपर है, तो उसे ओवरराइड करने के लिए स्पष्ट रूट
@app.errorhandler(404)
def page_not_found(e):
    # अगर यूजर विशेष रूप से वॉइस वेबहुक मांग रहा है और गलती से यहाँ आया, तो भी XML दे सकते हैं
    if request.path == '/voice-webhook':
        response = VoiceResponse()
        response.say("नमस्ते! ध्रुव एकेडमी में आपका स्वागत है।", voice='Polly.Aditi', language='hi-IN')
        return str(response), 200, {'Content-Type': 'application/xml'}
    
    # बाकी पेजों के लिए आपका पुराना होमपेज या नॉर्मल रेंडर
    return render_template('index.html'), 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

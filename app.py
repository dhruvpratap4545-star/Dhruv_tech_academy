from flask import Flask, Response

app = Flask(__name__)

@app.route('/')
def home():
    return "Dhruv Academy Server is Live!"

@app.route('/voice-webhook', methods=['GET', 'POST'])
def voice_webhook():
    # एक्सोटेल के लिए सही XML रिस्पॉन्स फॉर्मेट
    xml_response = """<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Say language="hi-IN">ध्रुव एकेडमी में आपका स्वागत है।</Say>
    </Response>"""
    
    return Response(xml_response, mimetype='text/xml')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

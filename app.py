from flask import Flask, request

# सबसे पहले 'app' को यहाँ परिभाषित करना जरूरी है
app = Flask(__name__)


# इसके बाद ही आप रूट्स (Routes) लिख सकते हैं
@app.route('/exotel-webhook', methods=['GET', 'POST'])
def exotel_webhook():
  try:
    caller_id = request.values.get('CallFrom')
    print(f'Exotel Call Received from: {caller_id}')

    xml_response = """<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say>नमस्ते! ध्रुव एकेडमी में आपका स्वागत है। आपके प्रतियोगी परीक्षाओं और स्मार्ट लर्निंग के नए मॉड्यूल्स अब लाइव हो चुके हैं।</Say>
        </Response>"""
    return xml_response, 200, {'Content-Type': 'application/xml'}
  except Exception as e:
    error_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say>Error occurred: {str(e)}</Say>
        </Response>"""
    return error_xml, 200, {'Content-Type': 'application/xml'}


@app.route('/')
def home():
  return 'Dhruv Academy Server is Live!'


if __name__ == '__main__':
  app.run(host='0.0.0.0', port=5000)

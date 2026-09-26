@app.route('/voice-webhook', methods=['GET', 'POST'])
def voice_webhook():
  try:
    # एक्सोटेल से आने वाले पैरामीटर्स को पढ़ना (जैसे किसने कॉल किया)
    caller_id = request.values.get('CallFrom')
    print(f'Exotel Call Received from: {caller_id}')

    # एक्सोटेल के लिए सही XML रिस्पांस
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

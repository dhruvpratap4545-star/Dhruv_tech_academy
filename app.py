@app.route('/exotel-webhook', methods=['GET', 'POST'])
def exotel_webhook():
  try:
    # एक्सोटेल द्वारा भेजे जाने वाले पैरामीटर्स कैप्चर करें
    caller_id = request.values.get('CallFrom')
    call_sid = request.values.get('CallSid')
    print(f'Exotel Call Received from: {caller_id}, SID: {call_sid}')

    # एक्सोटेल के लिए रिस्पांस (आप यहाँ टेक्स्ट या रीडायरेक्ट लिंक दे सकते हैं)
    # एक्सोटेल को प्ले या से करने के लिए आप अपना ऑडियो या टेक्स्ट रिस्पांस सेट कर सकते हैं
    return (
        '<?xml version="1.0" encoding="UTF-8"?><Response><Say>नमस्ते! ध्रुव'
        ' अकादमी में आपका स्वागत है।</Say></Response>',
        200,
        {'Content-Type': 'application/xml'},
    )
  except Exception as e:
    return f'Error: {str(e)}', 500

# Python का आधिकारिक हल्का वर्ज़न लें
FROM python:3.10-slim

# वर्किंग डायरेक्टरी सेट करें
WORKDIR /app

# जरूरी सिस्टम डिपेंडेंसी इंस्टॉल करें
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# पहले requirements फाइल कॉपी करें और इंस्टॉल करें (ताकि कैशिंग अच्छी रहे)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# बाकी सारा प्रोजेक्ट कोड कॉपी करें
COPY . .

# Cloud Run के लिए पोर्ट 8080 सेट करें और ऐप रन करें (अगर streamlit है तो streamlit run app.py, या जो भी आपकी मुख्य फाइल हो)
ENV PORT=8080
EXPOSE 8080

# अपनी मुख्य फाइल का नाम यहाँ दें (जैसे app.py या main.py)
CMD streamlit run app.py --server.port=8080 --server.address=0.0.0.0

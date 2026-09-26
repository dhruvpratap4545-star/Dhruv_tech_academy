const dhruvLang = {
    en: {
        brand: "Dhruv Academy Master Ecosystem",
        hero_title: "AI & 4D Holographic Education Ecosystem",
        hero_subtitle: "Access all 12 specialized AI learning and management modules.",

        // 12 Modules Data
        mod1_title: "3D Digital Blackboard",
        mod1_desc: "Interactive scientific simulation and live studio.",
        mod1_btn: "Open Blackboard",

        mod2_title: "Kids Zone",
        mod2_desc: "Fun animations, alphabets, and 3D learning for children.",
        mod2_btn: "Enter Kids Zone",

        mod3_title: "Coaching Hub",
        mod3_desc: "Personalized syllabus, live tracking, and study schedules.",
        mod3_btn: "Go to Coaching",

        mod4_title: "Digital Library",
        mod4_desc: "Verified knowledge matrix, notes, and academic papers.",
        mod4_btn: "Browse Library",

        mod5_title: "Competition Solver",
        mod5_desc: "AI-driven solver for competitive entrance exams.",
        mod5_btn: "Solve Questions",

        mod6_title: "Spoken English",
        mod6_desc: "Interactive conversational AI tutor for language fluency.",
        mod6_btn: "Start Speaking",

        mod7_title: "Legal AI",
        mod7_desc: "Statutory provisions, legal draftings, and RTI tools.",
        mod7_btn: "Open Legal AI",

        mod8_title: "AI Core Engine",
        mod8_desc: "Central neural network configuration and API bridges.",
        mod8_btn: "Manage Core",

        mod9_title: "AI Auto Healing",
        mod9_desc: "Automated ecosystem diagnostics and error correction.",
        mod9_btn: "Run Diagnostics",

        mod10_title: "AI YouTube Studio",
        mod10_desc: "Automatic lecture generation and streaming studio.",
        mod10_btn: "Launch Studio",

        mod11_title: "Central Wallet",
        mod11_desc: "Subscription billing, credits, and coin management.",
        mod11_btn: "Open Wallet",

        mod12_title: "Note Generator & Shield",
        mod12_desc: "Truth-filtered academic note synthesis and protection.",
        mod12_btn: "Generate Notes"
    },
    hi: {
        brand: "ध्रुव एकेडमी मास्टर इकोसिस्टम",
        hero_title: "एआई और 4D होलोग्राफिक शिक्षा इकोसिस्टम",
        hero_subtitle: "सभी 12 विशेष एआई शिक्षण एवं प्रबंधन मॉड्यूल्स का उपयोग करें।",

        // 12 मॉड्यूल्स का डेटा
        mod1_title: "3D डिजिटल ब्लैकबोर्ड",
        mod1_desc: "इंटरएक्टिव वैज्ञानिक सिमुलेशन और लाइव स्टूडियो।",
        mod1_btn: "ब्लैकबोर्ड खोलें",

        mod2_title: "किड्स ज़ोन",
        mod2_desc: "बच्चों के लिए मजेदार एनिमेशन, अक्षर और 3D सीख।",
        mod2_btn: "किड्स ज़ोन में जाएँ",

        mod3_title: "कोचिंग हब",
        mod3_desc: "कस्टमाइज्ड सिलेबस, लाइव प्रोग्रेस और स्टडी शेड्यूल।",
        mod3_btn: "कोचिंग हब खोलें",

        mod4_title: "डिजिटल लाइब्रेरी",
        mod4_desc: "सत्यापित नॉलेज मैट्रिक्स, नोट्स और अकादमिक संदर्भ।",
        mod4_btn: "लाइब्रेरी देखें",

        mod5_title: "कंपटीशन सॉल्वर",
        mod5_desc: "प्रतियोगी परीक्षाओं के लिए एआई आधारित प्रश्न समाधान।",
        mod5_btn: "प्रश्न हल करें",

        mod6_title: "स्पोकन इंग्लिश",
        mod6_desc: "फ्लुएंसी और बातचीत के लिए लाइव एआई ट्यूटर।",
        mod6_btn: "बोलना सीखें",

        mod7_title: "लीगल एआई",
        mod7_desc: "कानूनी प्रारूप, आरटीआई और विधिक परामर्श टूल।",
        mod7_btn: "लीगल एआई खोलें",

        mod8_title: "एआई कोर इंजन",
        mod8_desc: "केंद्रीय न्यूरल नेटवर्क और बैकएंड एपीआई ब्रिज।",
        mod8_btn: "कोर मैनेज करें",

        mod9_title: "एआई ऑटो हीलिंग",
        mod9_desc: "सिस्टम डायग्नोस्टिक्स और ऑटोमैटिक एरर सुधार।",
        mod9_btn: "डायग्नोस्टिक्स चलाएँ",

        mod10_title: "एआई यूट्यूब स्टूडियो",
        mod10_desc: "ऑटोमैटिक लेक्चर जनरेशन और वीडियो पब्लिशिंग।",
        mod10_btn: "स्टूडियो खोलें",

        mod11_title: "सेंट्रल वॉलेट",
        mod11_desc: "सब्सक्रिप्शन, टोकन बैलेंस और ट्रांजैक्शन।",
        mod11_btn: "वॉलेट खोलें",

        mod12_title: "नोट जनरेटर व शील्ड",
        mod12_desc: "ट्रुथ-फिल्टर्ड अकादमिक नोट्स तैयार करें व सुरक्षित रखें।",
        mod12_btn: "नोट्स बनाएँ"
    }
};

function setLanguage(lang) {
    document.querySelectorAll('[data-key]').forEach(el => {
        const key = el.getAttribute('data-key');
        if (dhruvLang[lang] && dhruvLang[lang][key]) {
            el.innerText = dhruvLang[lang][key];
        }
    });
    localStorage.setItem('user_lang', lang);
}
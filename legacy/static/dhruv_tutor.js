/**
 * Dhruv Academy Master AI Tutor Engine (Production Grade)
 * Zero API Cost | Multi-topic | Bilingual | Algorithm-Ready
 */

class DhruvMasterTutor {
    constructor() {
        this.synth = window.speechSynthesis;
        this.currentUtterance = null;
        this.typeInterval = null;
        this.selectedVoice = null;
        this.initUI();
        this.loadVoices();
    }

    loadVoices() {
        const updateVoices = () => {
            const voices = this.synth.getVoices();
            // हिंदी और भारतीय अंग्रेजी प्राथमिकताओं की खोज
            this.hindiVoice = voices.find(v => v.lang.includes('hi')) || null;
            this.englishVoice = voices.find(v => v.lang.includes('en-IN') || v.lang.includes('en-GB') || v.lang.includes('en-US')) || null;
        };
        updateVoices();
        if (speechSynthesis.onvoiceschanged !== undefined) {
            speechSynthesis.onvoiceschanged = updateVoices;
        }
    }

    initUI() {
        if (document.getElementById('dhruv-master-ecosystem')) return;

        const container = document.createElement('div');
        container.id = 'dhruv-master-ecosystem';
        container.innerHTML = `
            <style>
                #dhruv-master-ecosystem {
                    display: grid;
                    grid-template-columns: 340px 1fr;
                    gap: 20px;
                    background: #0d1117;
                    border: 2px solid #30363d;
                    border-radius: 14px;
                    padding: 20px;
                    max-width: 1200px;
                    margin: 25px auto;
                    box-shadow: 0 12px 35px rgba(0,0,0,0.6);
                    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
                    box-sizing: border-box;
                }
                @media (max-width: 850px) {
                    #dhruv-master-ecosystem { grid-template-columns: 1fr; }
                }
                .dhruv-avatar-pane {
                    display: flex;
                    flex-direction: column;
                    background: #161b22;
                    border-radius: 10px;
                    border: 1px solid #30363d;
                    overflow: hidden;
                }
                .dhruv-video-box {
                    width: 100%;
                    height: 280px;
                    background: #000;
                    position: relative;
                }
                .dhruv-video-box video {
                    width: 100%;
                    height: 100%;
                    object-fit: cover;
                }
                .dhruv-status-bar {
                    padding: 10px;
                    text-align: center;
                    font-size: 13px;
                    font-weight: 600;
                    background: #21262d;
                    color: #58a6ff;
                    border-top: 1px solid #30363d;
                }
                .dhruv-board-pane {
                    background: #081c15;
                    border: 8px solid #3e2723;
                    border-radius: 10px;
                    box-shadow: inset 0 0 25px rgba(0,0,0,0.9);
                    padding: 20px;
                    display: flex;
                    flex-direction: column;
                    min-height: 380px;
                }
                .board-header {
                    border-bottom: 2px dashed #2e7d32;
                    padding-bottom: 8px;
                    margin-bottom: 12px;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }
                .board-title {
                    font-size: 20px;
                    font-weight: 700;
                    color: #a5d6a7;
                    margin: 0;
                }
                .board-badge {
                    background: #1b4332;
                    color: #d8f3dc;
                    padding: 4px 10px;
                    border-radius: 4px;
                    font-size: 12px;
                }
                #dhruv-chalk-content {
                    flex-grow: 1;
                    font-size: 16px;
                    line-height: 1.7;
                    color: #f1faee;
                    white-space: pre-wrap;
                    overflow-y: auto;
                    max-height: 320px;
                }
                .dhruv-code-block {
                    background: rgba(0,0,0,0.4);
                    border-left: 4px solid #00e676;
                    padding: 10px;
                    margin: 10px 0;
                    font-family: 'Courier New', monospace;
                    color: #69f0ae;
                }
                .dhruv-controls {
                    display: flex;
                    justify-content: flex-end;
                    gap: 10px;
                    margin-top: 15px;
                }
                .dhruv-btn {
                    padding: 8px 18px;
                    font-size: 14px;
                    font-weight: 600;
                    border-radius: 6px;
                    border: none;
                    cursor: pointer;
                    transition: 0.2s ease;
                }
                .dhruv-btn-stop {
                    background: #d32f2f;
                    color: #fff;
                }
                .dhruv-btn-stop:hover { background: #b71c1c; }
            </style>

            <div class="dhruv-avatar-pane">
                <div class="dhruv-video-box">
                    <video id="dhruvMasterVideo" loop muted playsinline>
                        <source src="/static/dhruv_academy.mp4" type="video/mp4">
                    </video>
                </div>
                <div class="dhruv-status-bar" id="dhruvStatus">ध्रुव एकेडमी • एआई ट्यूटर तैयार</div>
            </div>

            <div class="dhruv-board-pane">
                <div class="board-header">
                    <h2 class="board-title" id="dhruvBoardTitle">अकादमिक ब्लैकबोर्ड</h2>
                    <span class="board-badge" id="dhruvLangBadge">Bilingual AI</span>
                </div>
                <div id="dhruv-chalk-content">लेक्चर शुरू होने पर यहाँ नोट्स और विश्लेषण लाइव प्रदर्शित होंगे...</div>
                <div class="dhruv-controls">
                    <button class="dhruv-btn dhruv-btn-stop" id="dhruvStopBtn">रोकें (Stop)</button>
                </div>
            </div>
        `;

        document.body.prepend(container);

        this.video = document.getElementById('dhruvMasterVideo');
        this.chalkBoard = document.getElementById('dhruv-chalk-content');
        this.boardTitle = document.getElementById('dhruvBoardTitle');
        this.langBadge = document.getElementById('dhruvLangBadge');
        this.statusBar = document.getElementById('dhruvStatus');

        document.getElementById('dhruvStopBtn').onclick = () => this.stopLecture();
    }

    /**
     * सार्वभौमिक लेक्चर फंक्शन (Universal Teach Engine)
     * @param {string} title - अध्याय / विषय का नाम
     * @param {string} speechText - जो आवाज़ में बोला जाएगा (व्याख्या)
     * @param {string} boardText - जो ब्लैकबोर्ड पर लिखा जाएगा (फॉर्मूला, कोड, बुलेट्स)
     * @param {string} lang - 'hi-IN' (हिंदी) या 'en-US' (अंग्रेजी)
     */
    teach({ title, speechText, boardText, lang = 'hi-IN' }) {
        this.stopLecture();

        this.boardTitle.innerText = title;
        this.langBadge.innerText = lang.includes('hi') ? 'हिंदी माध्यम' : 'English Medium';
        this.statusBar.innerText = "व्याख्यान प्रगति पर है...";
        this.chalkBoard.innerHTML = '';

        // अवतार का विजुअल मोशन शुरू
        this.video.currentTime = 0;
        this.video.play().catch(() => {
            console.log("Autoplay waiting for user gesture.");
        });

        // स्पीच सिंथेसाइज़र सेटअप
        this.currentUtterance = new SpeechSynthesisUtterance(speechText);
        this.currentUtterance.lang = lang;
        
        // ध्रुव आवाज़ प्रोफाइल कैलिब्रेशन (गंभीर, स्पष्ट और स्थिर टोन)
        this.currentUtterance.pitch = 0.95; 
        this.currentUtterance.rate = 0.92;

        if (lang.includes('hi') && this.hindiVoice) {
            this.currentUtterance.voice = this.hindiVoice;
        } else if (this.englishVoice) {
            this.currentUtterance.voice = this.englishVoice;
        }

        // डायनामिक ब्लैकबोर्ड राइटिंग (स्मार्ट सिंक)
        let index = 0;
        const totalChars = boardText.length;
        const estimatedDurationMs = Math.max(8000, speechText.length * 65);
        const charInterval = Math.max(15, estimatedDurationMs / totalChars);

        this.typeInterval = setInterval(() => {
            if (index < totalChars) {
                this.chalkBoard.innerText += boardText[index];
                this.chalkBoard.scrollTop = this.chalkBoard.scrollHeight;
                index++;
            } else {
                clearInterval(this.typeInterval);
            }
        }, charInterval);

        // लेक्चर समाप्त होने पर
        this.currentUtterance.onend = () => {
            this.finishLecture(boardText);
        };

        this.currentUtterance.onerror = () => {
            this.finishLecture(boardText);
        };

        this.synth.speak(this.currentUtterance);
    }

    finishLecture(finalContent) {
        clearInterval(this.typeInterval);
        this.chalkBoard.innerText = finalContent;
        this.video.pause();
        this.statusBar.innerText = "व्याख्यान पूर्ण हुआ • ध्रुव एकेडमी";
    }

    stopLecture() {
        if (this.synth.speaking) this.synth.cancel();
        if (this.typeInterval) clearInterval(this.typeInterval);
        if (this.video) this.video.pause();
        this.statusBar.innerText = "सत्र रुका हुआ है";
    }
}

// ग्लोबल विंडो ऑब्जेक्ट बनाना
window.DhruvTutor = new DhruvMasterTutor();
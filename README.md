# 🎤 Bella - Personal AI Voice Assistant

> **Building the future of voice-activated AI.** Bella is an open-source personal AI assistant designed for voice interaction, multi-language support, and intelligent learning capabilities. Inspired by JARVIS, Bella brings conversational AI to your fingertips.

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Open Source](https://img.shields.io/badge/open-source-brightgreen.svg)]()

---

## 🚀 Features

- **🎤 Voice Recognition** - Real-time voice input using Termux API
- **🧠 AI-Powered Brain** - Integrates Google Generative AI (Gemini 1.5 Flash)
- **🌐 Multi-Language Support** - Translation capabilities across 5+ languages
- **📱 Mobile-First** - Runs on Android via Termux
- **🔊 Text-to-Speech** - Natural voice output synthesis
- **⚡ Lightweight** - Minimal dependencies, maximum performance
- **🛠️ Customizable** - Easy to extend with new features

---

## 📋 Quick Start

### Prerequisites
- Python 3.8 or higher
- [Termux](https://termux.com/) (for Android support)
- Google API Key (free at [AI Studio](https://aistudio.google.com/))

### Installation

```bash
# Clone the repository
git clone https://github.com/edwardparkinson-star/Bella.git
cd Bella

# Install dependencies
pip install google-generativeai

# (Android Only) Install Termux API
pkg install termux-api

# Run Bella
python bella.py
```

### Configuration

1. Get your free API key from [Google AI Studio](https://aistudio.google.com/)
2. Open `bella.py` and replace `YOUR_FREE_API_KEY_HERE` with your actual key
3. Run the script!

```python
self.API_KEY = "YOUR_FREE_API_KEY_HERE"
```

---

## 💡 Usage Examples

### Voice Commands
```
You: "Hello Bella"
Bella: "Hello Edward! I am running offline right now."

You: "translate hello to spanish"
Bella: "In spanish, that is: hola"

You: "What is the capital of France?"
Bella: "The capital of France is Paris."

You: "exit"
Bella: "Shutting down. Goodbye!"
```

### Offline Mode
Bella works without an API key but with limited functionality:
- Basic greetings
- Pre-defined translations
- Hardcoded commands

### Online Mode (with API Key)
- Full AI conversations
- Advanced question answering
- Creative responses
- Real-time learning

---

## 🏗️ Architecture

```
Bella/
├── bella.py              # Main application
├── README.md             # Project documentation
├── CONTRIBUTING.md       # Contribution guidelines
├── ROADMAP.md            # Future plans
└── docs/
    ├── API_SETUP.md      # Google API configuration
    ├── ARCHITECTURE.md   # Technical deep dive
    └── TROUBLESHOOTING.md # Common issues & fixes
```

---

## 🤝 Contributing

We're actively seeking contributors! Here's how you can help:

### 🎯 We're Looking For:
- **API Specialists** - Integrate additional AI/ML APIs (OpenAI, Anthropic, etc.)
- **Voice Recognition Experts** - Improve speech-to-text accuracy
- **NLP Engineers** - Enhance language understanding
- **Mobile Developers** - Expand Android/iOS support
- **Documentation Writers** - Improve guides and tutorials

### 📖 Contribution Areas:
- [ ] Add support for new APIs
- [ ] Improve voice recognition accuracy
- [ ] Add more language support
- [ ] Create desktop/web UI
- [ ] Implement offline AI models
- [ ] Add smart home integration
- [ ] Improve error handling

👉 **See [CONTRIBUTING.md](./CONTRIBUTING.md) for detailed instructions**

---

## 💬 Join Our Community & Discussions

We're open to **GitHub Discussions** about:
- Feature ideas and suggestions
- Technical architecture decisions
- API recommendations
- Integration possibilities
- Best practices for voice AI
- Real-world use cases

**[Start a Discussion](https://github.com/edwardparkinson-star/Bella/discussions)** - Share your thoughts, ask questions, or propose improvements!

---

## 🔗 Current APIs & Integrations

### ✅ Currently Integrated:
- **Google Generative AI (Gemini 1.5 Flash)** - Main conversational AI

### 🔄 Planned Integrations:
- OpenAI GPT-4 / ChatGPT
- Anthropic Claude
- Hugging Face Models
- Local LLMs (Ollama, LLaMA)
- Spotify Integration
- Weather APIs
- News Aggregation

### 🤔 Potential APIs We're Considering:
- Microsoft Azure Cognitive Services
- AWS Polly (advanced TTS)
- IBM Watson
- ElevenLabs (premium voice synthesis)

**Have an API suggestion?** [Open a Discussion](https://github.com/edwardparkinson-star/Bella/discussions) or submit an issue!

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| **Language** | Python 3.8+ |
| **AI Engine** | Google Generative AI SDK |
| **Voice I/O** | Termux API (Android) |
| **Text-to-Speech** | Termux TTS Engine |
| **Speech-to-Text** | Termux Speech Recognition |
| **CLI** | Pure Python |

---

## 📊 Roadmap

### Phase 1: Core Functionality ✅
- Voice recognition
- Basic AI responses
- Multi-language support

### Phase 2: Expansion (In Progress)
- [ ] Multiple API integrations
- [ ] Desktop application
- [ ] Web interface
- [ ] User authentication

### Phase 3: Advanced Features (Planned)
- [ ] Machine learning personalization
- [ ] Smart home device control
- [ ] Calendar/scheduling integration
- [ ] Task automation
- [ ] Custom skill development

---

## 🐛 Troubleshooting

### Issue: "termux-api not found"
```bash
pkg install termux-api
```

### Issue: API key not working
1. Verify API key at [AI Studio](https://aistudio.google.com/)
2. Check you've replaced `YOUR_FREE_API_KEY_HERE` in the code
3. Ensure `google-generativeai` is installed: `pip install --upgrade google-generativeai`

### Issue: Voice not working
- Ensure Termux has microphone permissions
- Test with: `termux-speech-to-text`
- Check Termux API is running

📖 **[Full Troubleshooting Guide](./docs/TROUBLESHOOTING.md)**

---

## 📚 Documentation

- **[API Setup Guide](./docs/API_SETUP.md)** - Configure Google API keys
- **[Architecture Overview](./docs/ARCHITECTURE.md)** - Understand the codebase
- **[Contributing Guide](./CONTRIBUTING.md)** - How to contribute
- **[Roadmap](./ROADMAP.md)** - Future development plans

---

## 🌟 Getting Google's Attention

We're building Bella to showcase the potential of Google's AI APIs. If you're from Google or interested in partnership opportunities:

1. **Try Bella** - Test our implementation with Google Gemini API
2. **Join Discussions** - Share your feedback and ideas
3. **Contribute** - Help us improve the Google AI integration
4. **Contact** - Open an issue or discussion about collaboration

---

## 📝 License

Bella is licensed under the **GNU General Public License v3.0**. See [LICENSE](./LICENSE) file for details.

---

## 🙏 Acknowledgments

- Google Generative AI SDK team
- Termux development community
- All our future contributors

---

## 📞 Contact & Support

- **GitHub Issues** - [Report bugs or request features](https://github.com/edwardparkinson-star/Bella/issues)
- **GitHub Discussions** - [Join community conversations](https://github.com/edwardparkinson-star/Bella/discussions)
- **Creator** - [@edwardparkinson-star](https://github.com/edwardparkinson-star)

---

## 🔔 Star & Watch

If you find Bella interesting, please consider:
- ⭐ **Starring** the repository
- 👀 **Watching** for updates
- 🔗 **Sharing** with fellow developers
- 💬 **Joining discussions** to help shape the future

---

**Built with ❤️ by developers, for developers. Let's build the future of AI assistants together!**

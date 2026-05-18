# Bella



import os
import subprocess

# --- SETUP THE BRAIN ---
try:
    import google.generativeai as genai
    # PASTE YOUR KEY HERE
    API_KEY = "API_KEY" 
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    HAS_BRAIN = True
except ImportError:
    HAS_BRAIN = False

class BellaAI:
    def speak(self, text):
        print(f"Bella: {text}")
        os.system(f'termux-tts-speak "{text}"')

    def listen(self):
        """Uses Termux microphone to listen to you."""
        print("Listening...")
        try:
            # This triggers the Android voice recognition popup
            result = subprocess.check_output(["termux-speech-to-text"], stderr=subprocess.STDOUT)
            return result.decode('utf-8').strip().lower()
        except Exception:
            return ""

    def run(self):
        self.speak("Bella is online and listening.")
        
        while True:
            # 1. Listen for your voice
            user_speech = self.listen()
            
            if not user_speech:
                continue
                
            print(f"You said: {user_speech}")

            # 2. Check for exit commands
            if any(word in user_speech for word in ['stop', 'exit', 'goodbye']):
                self.speak("Goodbye Edward.")
                break

            # 3. Process with "Internet Brain"
            if HAS_BRAIN and API_KEY != "API_KEY":
                try:
                    response = model.generate_content(user_speech)
                    self.speak(response.text)
                except Exception:
                    self.speak("I'm having trouble connecting to my brain.")
            else:
                self.speak("I heard you, but I need my API key to learn more.")

if __name__ == "__main__":
    bella = BellaAI()
    bella.run()
import os
import sys

# Try to import the Google AI library for the "Internet Brain"
try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

class BellaAI:
    def __init__(self):
        # --- CONFIGURATION ---
        # Get a free key at: https://aistudio.google.com/
        self.API_KEY = "YOUR_FREE_API_KEY_HERE"
        
        if HAS_GENAI and self.API_KEY != "YOUR_FREE_API_KEY_HERE":
            genai.configure(api_key=self.API_KEY)
            self.model = genai.GenerativeModel('gemini-1.5-flash')
            self.online_mode = True
        else:
            self.online_mode = False

        # Fixed Dictionary Syntax
        self.phrases = {
            'my name is edward': {
                'spanish': 'mi nombre es edward',
                'french': 'mon nom est edward',
                'german': 'mein name ist edward',
                'italian': 'il mio nome è edward',
                'mandarin': 'Wǒ de míngzì shì Edward'
            },
            'hello': {
                'spanish': 'hola',
                'french': 'bonjour',
                'german': 'hallo',
                'italian': 'ciao',
                'mandarin': 'Nǐ hǎo'
            },
            'goodbye': {
                'spanish': 'adiós',
                'french': 'au revoir',
                'german': 'auf wiedersehen',
                'italian': 'arrivederci',
                'mandarin': 'Zài jiàn'
            }
        }
        
        print("✓ BellaAI initialized successfully")
        if not self.online_mode:
            print("⚠ Note: Running in Offline Mode. Add API Key for Internet Learning.")

    def speak(self, text):
        """Uses Termux-API to speak. Ensure termux-api is installed."""
        print(f"Bella: {text}")
        # Clean text of quotes to avoid terminal errors
        safe_text = text.replace('"', '')
        # Direct command to Termux's internal TTS engine
        os.system(f'termux-tts-speak "{safe_text}"')

    def listen_text_input(self, prompt_message="Your input"):
        try:
            text = input(f"{prompt_message}: > ")
            return text.strip()
        except (EOFError, KeyboardInterrupt):
            return "exit"

    def run(self):
        self.speak("System initialized. Bella is online.")
        
        while True:
            query = self.listen_text_input("You").lower()

            if not query:
                continue

            if any(word in query for word in ['stop', 'exit', 'quit', 'bye']):
                self.speak("Shutting down. Goodbye!")
                break

            # --- Logic: Translation ---
            elif 'translate' in query:
                self.speak("What phrase should I translate?")
                phrase = self.listen_text_input("Phrase").lower()
                self.speak("Which language? (spanish, french, german, italian, mandarin)")
                lang = self.listen_text_input("Language").lower()
                
                if phrase in self.phrases and lang in self.phrases[phrase]:
                    result = self.phrases[phrase][lang]
                    self.speak(f"In {lang}, that is: {result}")
                else:
                    self.speak("I don't have that specific phrase saved.")

            # --- Logic: Internet Learning (The Brain) ---
            elif self.online_mode:
                # If it's not a hardcoded command, Bella uses her "Internet Brain"
                try:
                    response = self.model.generate_content(query)
                    self.speak(response.text)
                except Exception as e:
                    self.speak("I had trouble reaching my internet brain.")
            
            else:
                # Default Offline Responses
                if "hello" in query:
                    self.speak("Hello Edward! I am running offline right now.")
                elif "who are you" in query:
                    self.speak("I am Bella, your personal AI assistant.")
                else:
                    self.speak("I'm not sure how to do that offline. Please add my API key!")

if __name__ == "__main__":
    # Check if Termux:API is accessible
    if os.system('command -v termux-tts-speak > /dev/null 2>&1') != 0:
        print("Error: 'termux-api' not found. Run 'pkg install termux-api' in Termux first.")
    
    bella = BellaAI()
    bella.run()
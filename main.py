# jarvis.py
import os
import time
import webbrowser
import traceback
import requests
import speech_recognition as sr

# TTS choices: gTTS + pygame (online) with pyttsx3 fallback (offline)
from gtts import gTTS
import pygame
import pyttsx3

# Local modules (examples below)
# client.py will export OPENAI_API_KEY and NEWS_API_KEY (strings)
# musicLibrary.py will export music (dict mapping normalized song-name -> url)
try:
    import client
except Exception:
    client = None

try:
    import musicLibrary
except Exception:
    musicLibrary = None

# Optional OpenAI wrapper (if you have openai package configured)
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

# Config: default to values from client.py if present
OPENAI_API_KEY = getattr(client, "OPENAI_API_KEY", None)
NEWS_API_KEY = getattr(client, "NEWS_API_KEY", None)

# Use a local temp file for gTTS playback
TMP_TTS = "tmp_tts.mp3"

# Initialize pyttsx3 (fallback)
pytt_engine = pyttsx3.init()

def speak_with_pygame(text):
    """Use gTTS to create an mp3 and play with pygame. Falls back to pyttsx3 on errors."""
    try:
        tts = gTTS(text=text, lang="en")
        tts.save(TMP_TTS)

        pygame.mixer.init()
        pygame.mixer.music.load(TMP_TTS)
        pygame.mixer.music.play()

        # wait until playback finishes
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)

        pygame.mixer.music.unload()
        pygame.mixer.quit()
        if os.path.exists(TMP_TTS):
            os.remove(TMP_TTS)
    except Exception as e:
        # fallback to pyttsx3
        print("gTTS/pygame failed, falling back to pyttsx3:", e)
        try:
            pytt_engine.say(text)
            pytt_engine.runAndWait()
        except Exception as e2:
            print("pytt fallback also failed:", e2)

def speak(text):
    # short wrapper to avoid blocking too long text at once
    if not text:
        return
    # chunk long text into smaller sentences so TTS works reliably
    chunks = [c.strip() for c in text.split(".") if c.strip()]
    for chunk in chunks:
        speak_with_pygame(chunk + ".")

def aiProcess(command):
    """Send the command to OpenAI (if configured). Returns string or error message."""
    if OPENAI_API_KEY is None or OpenAI is None:
        return "AI not configured. Please set OPENAI_API_KEY in client.py and install openai package."

    try:
        client_api = OpenAI(api_key=OPENAI_API_KEY)
        resp = client_api.chat.completions.create(
            model="gpt-5",
            messages=[
                {"role": "system", "content": "You are Jarvis, a virtual assistant and you are skilled in general tasks like alexa and google home."},
                {"role": "user", "content": command}
            ],
            max_tokens=250,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print("Error calling OpenAI:", e)
        traceback.print_exc()
        return "Sorry, I couldn't reach the AI service."

def get_headlines(country="in", page_size=5):
    """Return list of top headline titles (uses NEWS_API_KEY)."""
    if not NEWS_API_KEY:
        return ["News API key not configured. Put NEWS_API_KEY in client.py."]
    try:
        url = f"https://newsapi.org/v2/top-headlines?country=in&apiKey={NEWS_API_KEY}"
        r = requests.get(url, timeout=8)
        if r.status_code != 200:
            print("News API HTTP", r.status_code, r.text)
            return [f"Failed to fetch news: HTTP {r.status_code}"]
        data = r.json()
        articles = data.get("articles", [])
        if not articles:
            return ["No news articles found."]
        return [a.get("title", "Untitled") for a in articles]
    except Exception as e:
        print("Exception fetching news:", e)
        return ["Error fetching news."]

def normalize_key(s: str) -> str:
    return " ".join(s.lower().strip().split())

def handle_play_command(command_text):
    """Handle 'play' command. Supports:
       - 'play <song name>' where musicLibrary.music is a mapping
       - 'play <url>' opens the URL directly
    """
    remainder = command_text.lower().replace("play", "", 1).strip()
    if not remainder:
        speak("Which song should I play?")
        return

    # If it looks like a URL, open it
    if remainder.startswith("http://") or remainder.startswith("https://"):
        webbrowser.open(remainder)
        speak(f"Playing from URL.")
        return

    # If musicLibrary available, search for best match
    if musicLibrary and hasattr(musicLibrary, "music"):
        key = normalize_key(remainder)
        # direct match
        if key in musicLibrary.music:
            url = musicLibrary.music[key]
            webbrowser.open(url)
            speak(f"Playing {remainder}.")
            return
        # try partial substring match
        for k in musicLibrary.music:
            if key in k:
                webbrowser.open(musicLibrary.music[k])
                speak(f"Playing {k}.")
                return
        # try startswith
        for k in musicLibrary.music:
            if k.startswith(key):
                webbrowser.open(musicLibrary.music[k])
                speak(f"Playing {k}.")
                return

    # fallback: try search on YouTube
    query = remainder.replace(" ", "+")
    url = f"https://www.youtube.com/results?search_query={query}"
    webbrowser.open(url)
    speak(f"Couldn't find the exact song locally. Searching YouTube for {remainder}.")

def processCommand(c):
    c = c.strip()
    if not c:
        return

    lower = c.lower()

    try:
        if "open google" in lower:
            webbrowser.open("https://google.com")
            speak("Opening Google.")

        elif "open facebook" in lower:
            webbrowser.open("https://facebook.com")
            speak("Opening Facebook.")

        elif "open youtube" in lower:
            webbrowser.open("https://youtube.com")
            speak("Opening YouTube.")

        elif "open linkedin" in lower:
            webbrowser.open("https://linkedin.com")
            speak("Opening LinkedIn.")

        elif lower.startswith("play"):
            handle_play_command(c)

        elif "news" in lower:
            speak("Fetching the top headlines.")
            headlines = get_headlines()
            for h in headlines:
                speak(h)
                time.sleep(0.2)

        else:
            # fallback to AI
            speak("Let me check.")
            answer = aiProcess(c)
            speak(answer)

    except Exception as e:
        print("Error in processCommand:", e)
        traceback.print_exc()
        speak("Sorry, I encountered an error while processing the command.")

def listen_for_wakeword(recognizer, mic, wakeword="jarvis", timeout=6, phrase_time_limit=5):
    """Listen until the wakeword is heard. Returns True when wakeword detected."""
    try:
        print("Adjusting for ambient noise... (1 sec)")
        with mic as source:
            recognizer.adjust_for_ambient_noise(source, duration=1)
        print("Listening for wake word...")
        with mic as source:
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
        try:
            text = recognizer.recognize_google(audio)
            print("Heard (wake stage):", text)
            if wakeword.lower() in text.lower():
                return True
        except sr.UnknownValueError:
            # nothing recognized
            return False
        except sr.RequestError as e:
            print("Speech recognition request error:", e)
            return False
    except Exception as e:
        print("Exception listening for wakeword:", e)
    return False

def listen_for_command(recognizer, mic, timeout=None, phrase_time_limit=6):
    """Listen once and return recognized string or None."""
    try:
        with mic as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
        try:
            text = recognizer.recognize_google(audio)
            print("Command recognized:", text)
            return text
        except sr.UnknownValueError:
            return None
        except sr.RequestError as e:
            print("Speech recognition request error:", e)
            return None
    except Exception as e:
        print("Exception in listen_for_command:", e)
        return None

def main_loop():
    recognizer = sr.Recognizer()
    mic = sr.Microphone()

    speak("Initializing Jarvis.")
    time.sleep(0.3)

    try:
        while True:
            try:
                got_wake = listen_for_wakeword(recognizer, mic)
                if not got_wake:
                    # small sleep to avoid busy-looping
                    continue

                speak("Yes?")
                # listen for full command (allow more time)
                cmd = listen_for_command(recognizer, mic, timeout=6, phrase_time_limit=8)

                if not cmd:
                    speak("Sorry, I didn't catch that.")
                    continue

                # user might say "Jarvis play despacito" or just "play despacito"
                # remove wakeword if present
                cmd_clean = cmd
                if cmd_clean.lower().startswith("jarvis"):
                    cmd_clean = cmd_clean[len("jarvis"):].strip()

                processCommand(cmd_clean)

            except KeyboardInterrupt:
                speak("Shutting down. Goodbye.")
                break
            except Exception as e:
                print("Main loop exception:", e)
                traceback.print_exc()
                # continue listening after errors
                time.sleep(0.5)

    finally:
        try:
            pygame.mixer.quit()
        except Exception:
            pass

if __name__ == "__main__":
    main_loop()

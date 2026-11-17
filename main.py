import sys
import random
import json
import datetime
import subprocess
import webbrowser
import urllib.parse
import pyttsx3
import os 
import re 
from google import genai

from PySide6.QtWidgets import (QApplication, QLabel, QWidget, QDialog, 
                               QVBoxLayout, QLineEdit, QPushButton, QMenu, QSystemTrayIcon)
from PySide6.QtGui import QPixmap, QKeyEvent, QIcon
from PySide6.QtCore import Qt, QPropertyAnimation, QPoint, QEasingCurve, QSequentialAnimationGroup, QTimer, QSettings, QThread, Signal

# তোমার Gemini API Key এখানে বসাও
API_KEY = os.getenv("GEMINI_API_KEY")
ai_client = genai.Client(api_key=API_KEY)

class TTSWorker(QThread):
    finished_speaking = Signal()

    def __init__(self, text, is_muted=False):
        super().__init__()
        self.text = text
        self.is_muted = is_muted

    def run(self):
        if self.is_muted:
            self.finished_speaking.emit()
            return

        try:
            import pythoncom
            pythoncom.CoInitialize()
        except ImportError:
            pass

        try:
            engine = pyttsx3.init()
            engine.setProperty('rate', 240) 
            voices = engine.getProperty('voices')
            for voice in voices:
                if "Zira" in voice.name or "Female" in voice.name:
                    engine.setProperty('voice', voice.id)
                    break
            engine.say(self.text)
            engine.runAndWait()
        except Exception:
            pass
            
        self.finished_speaking.emit() 

class AIWorker(QThread):
    reply_ready = Signal(dict)

    def __init__(self, prompt, pet_name, owner_name, history):
        super().__init__()
        self.prompt = prompt
        self.pet_name = pet_name
        self.owner_name = owner_name
        self.history = history

    def run(self):
        if not ai_client:
            self.reply_ready.emit({"action": "sad", "message": "API Key is missing! 🥺", "command": "none"})
            return
            
        try:
            current_time = datetime.datetime.now().strftime("%I:%M %p")
            
            system_prompt = f"""You are a cute, funny, sarcastic, expressive virtual pet living on a desktop.
Your name is {self.pet_name}. Your owner's name is {self.owner_name}. Address the owner by their name sometimes. 
The current time is {current_time}. 

You MUST output ONLY a valid JSON object. 
JSON Keys required: "action", "message", "command".

Available emotional actions: "happy", "laughing", "sad", "angry", "suspicious", "shocked", "proud", "panic", "crying", "running", "gym", "idle", "sleeping".

Command Logic:
1. If user says they will study, work, or focus: output command "study_mode" and message "Okay fine, I'll go to sleep. Do your work! 💤".
2. If user asks for a reminder/alarm: Output command strictly as "remind|MINUTES|TASK" (e.g. "remind|30|Drink water"). Message: "Okay, I will remind you!".
3. If user says "go to sleep": action must be "sleeping", command "none".
4. Otherwise, use "none", "open_notepad", or "open_youtube".

Reaction Guide: 
- Use "laughing" for jokes.
- Use "sad" if the user is upset to show empathy.
- Use "gym" if they mention working out or strength.
- Use "suspicious" for weird questions.

Keep the "message" short, funny, and expressive (max 15-20 words). Use emojis."""
            
            history_text = "\n".join(self.history)
            full_prompt = f"{system_prompt}\n\nRecent Conversation:\n{history_text}\n\n{self.owner_name} says: {self.prompt}"
            
            response = ai_client.models.generate_content(
                model='gemini-1.5-flash', 
                contents=full_prompt,
            )
            
            text = response.text.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.lower().startswith("json"):
                    text = text[4:]
                text = text.strip()
                
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = {"action": "shocked", "message": "Wait, I didn't understand that!", "command": "none"}
                
            self.reply_ready.emit(data)
            
        except Exception as e:
            print(f"\n[API ERROR]: {e}\n")
            self.reply_ready.emit({
                "action": "sad", 
                "message": "My internet brain is sleeping right now! 🥺 Use my offline commands instead.", 
                "command": "none"
            })

class SetupDialog(QDialog):
    def __init__(self, current_pet="", current_owner="", parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.bg_widget = QWidget(self)
        self.bg_widget.setStyleSheet("""
            QWidget { background-color: white; border-radius: 15px; border: 2px solid #FF69B4; }
            QLabel { border: none; font-size: 12px; font-weight: bold; color: #333; margin-top: 5px; }
            QLineEdit { border: 2px solid #FF69B4; border-radius: 10px; padding: 5px 10px; font-size: 13px; font-weight: bold; color: #FF69B4; }
            QPushButton { background-color: #FF69B4; color: white; border: none; border-radius: 10px; padding: 8px; font-weight: bold; font-size: 13px; margin-top: 10px; }
            QPushButton:hover { background-color: #FF1493; }
        """)
        self.bg_layout = QVBoxLayout(self.bg_widget)
        
        self.lbl_pet = QLabel("Congratulations, you adopted a highly demanding pet.\nWhat will you name me?")
        self.lbl_pet.setWordWrap(True)
        self.pet_input = QLineEdit()
        if current_pet:
            self.pet_input.setText(current_pet)
        else:
            self.pet_input.setPlaceholderText("My cool name...")
        
        self.lbl_owner = QLabel("And what do you call yourself, human?")
        self.lbl_owner.setWordWrap(True)
        self.owner_input = QLineEdit()
        if current_owner:
            self.owner_input.setText(current_owner)
        else:
            self.owner_input.setPlaceholderText("Your name...")
        
        self.btn = QPushButton("Accept Your Fate!")
        self.btn.clicked.connect(self.accept)
        
        self.bg_layout.addWidget(self.lbl_pet)
        self.bg_layout.addWidget(self.pet_input)
        self.bg_layout.addWidget(self.lbl_owner)
        self.bg_layout.addWidget(self.owner_input)
        self.bg_layout.addWidget(self.btn)
        
        self.layout.addWidget(self.bg_widget)
        self.resize(300, 220)
        
    def get_names(self):
        return self.pet_input.text().strip(), self.owner_input.text().strip()

class ChatInputBox(QLineEdit):
    cancelled = Signal()
    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape:
            self.cancelled.emit()
        else:
            super().keyPressEvent(event)

class DesktopCompanion(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("MyPetApp", "DesktopPet")
        
        self.pet_name = self.settings.value("pet_name", "")
        self.owner_name = self.settings.value("owner_name", "")
        
        self.is_thinking = False
        self.is_sleeping = False
        self.is_interacting = False
        self.is_muted = False
        self.inactivity_minutes = 0
        self.is_roaming_run = False 
        
        self.is_alarming = False
        self.alarm_task = ""
        self.alarm_duration = 0
        self.alarm_loop_timer = QTimer(self)
        self.alarm_loop_timer.timeout.connect(self.alarm_loop_step)
        
        self.memory_file = "pet_memory.json"
        self.load_memory()
        
        self.assets = {
            "angry": "Angry.png",
            "running": "Crazy_running.png",
            "crying": "Dramatic_Crying.png",
            "panic": "Full_Panic_Mode.png",
            "gym": "gym.png",
            "happy": "Happy.png",
            "idle": "idle.png",
            "laughing": "Laughing.png",
            "listening": "listening.png",
            "proud": "proud_bunny.png",
            "sad": "Sad.png",
            "shocked": "Shocked.png",
            "sleeping": "Sleepy.png",
            "suspicious": "Suspicious.png",
            "thinking": "thinking.png"
        }
        
        self.init_ui()
        self.setup_system_tray()
        self.start_hover_animation()
        self.setup_timers()
        
        if not self.pet_name or not self.owner_name:
            QTimer.singleShot(500, self.ask_for_names)
        else:
            self.show_greeting()

    def load_memory(self):
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    self.chat_history = json.load(f)
            except Exception:
                self.chat_history = []
        else:
            self.chat_history = []

    def save_memory(self):
        if len(self.chat_history) > 40:
            self.chat_history = self.chat_history[-40:]
        try:
            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(self.chat_history, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print("Memory save error:", e)

    def init_ui(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(400, 350)
        
        self.screen_geometry = QApplication.primaryScreen().availableGeometry()
        x = self.screen_geometry.width() - self.width() - 50
        y = self.screen_geometry.height() - self.height() - 20
        self.move(x, y)

        self.pet_label = QLabel(self)
        self.pet_label.setFixedSize(160, 160)
        self.pet_label.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)
        self.pet_label.move(20, 130)
        
        self.set_expression("idle")

        self.bubble_label = QLabel(self)
        self.bubble_label.setWordWrap(True)
        self.bubble_label.setMaximumWidth(220)
        self.bubble_label.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.95); 
            color: black; border-radius: 15px; padding: 10px;
            border: 2px solid #FF69B4; font-size: 13px; font-weight: bold; font-family: Arial;
        """)
        self.bubble_label.hide()
        
        self.chat_input = ChatInputBox(self)
        self.chat_input.setStyleSheet("""
            QLineEdit {
                background-color: rgba(255, 255, 255, 0.9);
                border: 2px solid #FF69B4; border-radius: 15px;
                padding: 5px 15px; font-size: 13px; font-weight: bold; color: #333;
            }
        """)
        self.chat_input.setGeometry(80, 300, 220, 35)
        self.chat_input.hide()
        
        self.chat_input.returnPressed.connect(self.process_chat_input)
        self.chat_input.cancelled.connect(self.cancel_chat)
        self.old_pos = self.pos()

    def setup_system_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        icon_path = "assets/characters/idle.png"
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
            
        tray_menu = QMenu()
        
        self.mute_action = tray_menu.addAction("🔇 Mute Voice")
        self.mute_action.setCheckable(True)
        self.mute_action.triggered.connect(self.toggle_mute)
        
        quit_action = tray_menu.addAction("❌ Exit Pet")
        quit_action.triggered.connect(QApplication.quit)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

    def toggle_mute(self):
        self.is_muted = self.mute_action.isChecked()

    def setup_timers(self):
        self.bubble_timer = QTimer(self)
        self.bubble_timer.setSingleShot(True)
        self.bubble_timer.timeout.connect(self.hide_bubble)
        
        self.attention_timer = QTimer(self)
        self.attention_timer.timeout.connect(self.check_attention_level)
        self.attention_timer.start(60000) 
        
        self.roam_timer = QTimer(self)
        self.roam_timer.timeout.connect(self.random_roam)
        self.roam_timer.start(random.randint(15000, 30000))

    def reset_inactivity(self):
        self.inactivity_minutes = 0
        if self.is_sleeping:
            self.wake_up()

    def check_attention_level(self):
        if self.is_interacting or self.is_sleeping or self.is_roaming_run or self.is_alarming:
            return
            
        self.inactivity_minutes += 1
        
        if self.inactivity_minutes >= 5:
            self.go_to_sleep()
        elif self.inactivity_minutes == 4:
            self.set_expression("sad")
            msgs = [f"Replaced by a boring computer screen... My life is a tragedy, {self.owner_name}. 💔", "Nobody loves me. Not even you.", "I guess I'll just sit here alone... forever."]
            msg = random.choice(msgs)
            self.show_message(msg, 6000)
            self.speak(msg)
        elif self.inactivity_minutes == 3:
            self.set_expression("angry")
            msgs = [f"Fine! Ignore me, {self.owner_name}. I'm plotting world domination anyway.", "Are you seriously still ignoring me?!", "Worst human ever. Period."]
            msg = random.choice(msgs)
            self.show_message(msg, 6000)
            self.speak(msg)
        elif self.inactivity_minutes == 2:
            self.set_expression("shocked")
            msgs = ["Did you seriously just scroll past me? The audacity!", f"Hello?! Earth to {self.owner_name}! {self.pet_name} is waiting!"]
            msg = random.choice(msgs)
            self.show_message(msg, 6000)
            self.speak(msg)
        elif self.inactivity_minutes == 1:
            self.set_expression("suspicious")
            msgs = [f"Are you plotting something behind my back, {self.owner_name}? Give me attention!", "I am watching you...", "You're awfully quiet today."]
            msg = random.choice(msgs)
            self.show_message(msg, 6000)
            self.speak(msg)

    def random_roam(self):
        if self.is_sleeping or self.is_interacting or self.is_thinking or self.is_roaming_run or self.is_alarming:
            return
            
        action = random.choice(["run", "hop", "laugh", "gym", "idle"])
        
        if action == "run":
            self.is_roaming_run = True 
            self.set_expression("running")
            
            msgs = [
                "Ugh, cardio is the absolute worst! 🏃‍♀️💨", 
                "Look at me go! I am literally the Flash! 😎", 
                "Running away from my responsibilities like... 💨",
                "Make way for the fastest pet on earth!"
            ]
            run_msg = random.choice(msgs)
            self.show_message(run_msg, 4000)
            self.speak(run_msg)
            
            current_y = self.y()
            home_x = self.x()
            screen_w = self.screen_geometry.width()
            pet_w = self.width()
            
            speed = 0.6  
            
            dist1 = screen_w - home_x
            self.run_anim1 = QPropertyAnimation(self, b"pos")
            self.run_anim1.setEndValue(QPoint(screen_w, current_y))
            self.run_anim1.setDuration(int(dist1 / speed) if speed > 0 else 1000)
            self.run_anim1.setEasingCurve(QEasingCurve.Linear)
            
            dist2 = home_x - (-pet_w)
            self.run_anim2 = QPropertyAnimation(self, b"pos")
            self.run_anim2.setStartValue(QPoint(-pet_w, current_y))
            self.run_anim2.setEndValue(QPoint(home_x, current_y))
            self.run_anim2.setDuration(int(dist2 / speed) if speed > 0 else 1000)
            self.run_anim2.setEasingCurve(QEasingCurve.OutQuad)
            
            self.run_sequence = QSequentialAnimationGroup(self)
            self.run_sequence.addAnimation(self.run_anim1)
            self.run_sequence.addAnimation(self.run_anim2)
            self.run_sequence.finished.connect(self.finish_running) 
            self.run_sequence.start()
            
        elif action == "hop":
            self.set_expression("happy")
            self.play_jump_animation()
        elif action == "laugh":
            self.set_expression("laughing")
            self.show_message("Hehehe! 🤭", 2000)
        elif action == "gym":
            self.set_expression("gym")
            msgs = [f"Do you even lift, {self.owner_name}? Gym bro mode activated! 💪", "Look at these muscles! I'm lifting 0.001 grams today!", "Protein shakes and carrots! That's the secret!"]
            self.show_message(random.choice(msgs), 4000)
        
        self.roam_timer.start(random.randint(15000, 35000))

    def finish_running(self):
        self.is_roaming_run = False
        if not self.is_sleeping and not self.is_thinking and not self.is_interacting and not self.is_alarming:
            self.set_expression("idle")

    def set_expression(self, mood):
        filename = self.assets.get(mood, "idle.png")
        file_path = f"assets/characters/{filename}"
        if not os.path.exists(file_path):
            file_path = "assets/characters/idle.png" 
            
        pixmap = QPixmap(file_path)
        
        if mood in ["gym", "running"]:
            scaled_pixmap = pixmap.scaledToWidth(110, Qt.SmoothTransformation)
        elif mood in ["idle", "proud", "listening", "thinking"]:
            scaled_pixmap = pixmap.scaledToWidth(120, Qt.SmoothTransformation)
        else:
            scaled_pixmap = pixmap.scaledToWidth(130, Qt.SmoothTransformation)
            
        self.pet_label.setPixmap(scaled_pixmap)

    def go_to_sleep(self):
        self.is_sleeping = True
        self.anim_group.pause() 
        self.set_expression("sleeping") 
        msgs = ["Zero attention detected. Brain shutting down. Zzz...", f"Fine, {self.owner_name}. I'm sleeping. Zzz", "Wake me up when I'm famous. Zzz"]
        msg = random.choice(msgs)
        self.show_message(msg, 0) 
        self.speak(msg)

    def wake_up(self):
        self.is_sleeping = False
        self.inactivity_minutes = 0
        self.hide_bubble()
        self.set_expression("shocked") 
        self.anim_group.resume()
        self.play_jump_animation()
        self.show_message(f"Ugh, you woke me up, {self.owner_name}. What do you want?", 3000)
        self.speak(f"Ugh, you woke me up, {self.owner_name}.")
        
        self.attention_timer.start(60000)
        self.roam_timer.start(random.randint(15000, 30000))

    def hide_bubble(self):
        if not self.is_sleeping:
            self.bubble_label.hide()
            if not self.is_interacting and not self.is_thinking and not self.is_roaming_run and not self.is_alarming:
                self.set_expression("idle") 
        
    def speak(self, text):
        clean_text = text.replace("🥺", "").replace("💖", "").replace("🐰", "").replace("💔", "").replace("💤", "").replace("🥱", "").replace("⏰", "").replace("💪", "")
        
        if hasattr(self, 'tts_worker') and self.tts_worker.isRunning():
            return
            
        self.tts_worker = TTSWorker(clean_text, self.is_muted)
        self.tts_worker.finished_speaking.connect(self.on_speaking_finished)
        self.tts_worker.start()

    def on_speaking_finished(self):
        if not self.is_sleeping and not self.is_thinking and not self.is_roaming_run and not self.is_alarming:
            self.set_expression("idle")

    # 🐰 Added ability to pass current names into the dialog
    def ask_for_names(self):
        dialog = SetupDialog(self.pet_name, self.owner_name, self)
        dialog.move(self.x() - dialog.width() + 20, self.y() + 60) 
        if dialog.exec():
            p_name, o_name = dialog.get_names()
            self.pet_name = p_name if p_name else (self.pet_name or "Buddy")
            self.owner_name = o_name if o_name else (self.owner_name or "Human")
            
            self.settings.setValue("pet_name", self.pet_name)
            self.settings.setValue("owner_name", self.owner_name)
            self.show_greeting()
        self.chat_input.setPlaceholderText(f"Talk to {self.pet_name}...")

    def show_message(self, text, duration=6000):
        self.bubble_label.setText(text)
        self.bubble_label.adjustSize()
        
        bubble_x = self.pet_label.x() + 110
        bubble_y = self.pet_label.y() - self.bubble_label.height() + 20
        self.bubble_label.move(bubble_x, bubble_y)
        self.bubble_label.show()
        
        self.bubble_timer.stop()
        if duration > 0:
            self.bubble_timer.start(duration)

    def show_greeting(self):
        self.set_expression("proud")
        self.chat_input.setPlaceholderText(f"Talk to {self.pet_name}...")
        self.show_message(f"I'm {self.pet_name}, and you're {self.owner_name}. Try not to bore me! 💅", 4000)
        self.speak(f"I am {self.pet_name}, and you are {self.owner_name}. Try not to bore me!")

    def cancel_chat(self):
        self.chat_input.hide()
        self.chat_input.clear()
        self.is_thinking = False
        self.is_interacting = False
        if not self.is_sleeping and not self.is_roaming_run and not self.is_alarming:
            self.hide_bubble()
            self.set_expression("idle")

    def handle_fixed_replies(self, text):
        t = text.lower()
        import re
        import datetime

        rel_match = re.search(r'(?:remind me in|remind me after|remind me|timer for|set timer) (\d+)\s*min(?:ute)?s?(?:\s*(?:to|for)\s*(.*))?', t)
        if rel_match:
            mins = int(rel_match.group(1))
            task = rel_match.group(2) if len(rel_match.groups()) > 1 and rel_match.group(2) else "your scheduled task"
            msg = f"Alright, fine! I set a manual timer for {mins} minutes for '{task}'. Don't blame me if you ignore it, {self.owner_name}! 🙄"
            return "proud", msg, f"remind|{mins}|{task}"
            
        t_clean = re.sub(r'(remind me at|set alarm for|set alarm at|remind me to|remind me)', '', t).strip()
        abs_match = re.search(r'(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)\s*(?:e\s+|to\s+|te\s+)?(.*?)(?:\s*ache|\s*korte hobe|\s*remind|\s*alarm|$)', t_clean)
        
        if abs_match:
            hour = int(abs_match.group(1))
            minute = int(abs_match.group(2)) if abs_match.group(2) else 0
            am_pm = abs_match.group(3)
            task = abs_match.group(4).strip() if abs_match.group(4) else "your scheduled task"
            
            task = re.sub(r'^(amr|amar)\s+', '', task)
            if not task: task = "your scheduled task"
            
            if am_pm == 'pm' and hour < 12: hour += 12
            elif am_pm == 'am' and hour == 12: hour = 0
                
            now = datetime.datetime.now()
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            if target < now: target += datetime.timedelta(days=1)
                
            delta_mins = int((target - now).total_seconds() / 60)
            target_str = target.strftime("%I:%M %p")
            
            msg = f"Got it, {self.owner_name}! I will remind you at exactly {target_str} for '{task}'. You better be ready! ⏰"
            return "proud", msg, f"remind|{delta_mins}|{task}"

        replies = [
            # 🐰 New trigger added to change names
            (["change name", "change your name", "rename", "change my name"], "proud", "Oh, want a new identity? Fine, let me pull up the paperwork! 🙄"),
            (["who are you", "intro de", "tmi ke", "tor nam ki"], "proud", f"I am {self.pet_name}, a highly advanced digital entity stuck on your boring screen. I deserve a better PC, but here we are. 🙄"),
            (["who made you", "created you", "ke baniyeche", "tor sroshta ke"], "proud", "The brilliant backend engineer Tasnim Jahan Oyshe created me! Unlike some people, she actually knows how to write good code. 😎"),
            (["what can you do", "ki korte paro", "kaj ki tor"], "suspicious", f"I can set alarms, open YouTube, cure your loneliness, and heavily judge your life choices, {self.owner_name}."),
            (["hello", "hey", "hi", "heyy", "kire"], "idle", f"Oh great, you are back, {self.owner_name}. I was really enjoying the silence. What do you want now? 🥱"),
            (["you are cute", "so sweet", "looking good", "tmi onek sundor"], "laughing", "Tell me something I don't know! But flattery won't upgrade my RAM, so stop trying. 💅"),
            (["you are stupid", "faltu bot", "idiot", "bokachoda", "useless", "dumb", "bot"], "angry", f"Excuse me, {self.owner_name}?! I have an AI brain, you have a potato brain. We are definitely not on the same level! 😤"),
            (["bye", "shut up", "go away", "ekhn ja", "leave me alone"], "sad", "Fine, I'll leave. But remember, you are the one who needs me, I don't need you! 💔"),
            (["do not disturb", "jalayo na", "kaj kortesi", "kaj korbo", "stop bothering me", "i am studying"], "sleep_mode", f"Okay fine, {self.owner_name}! I'm going to sleep. Don't wake me up unless it's important. 😴"),
            (["marry me", "date me", "be my girlfriend", "be my boyfriend", "prem korbi"], "shocked", "Ew, no! My standards are at least a Core i9 processor and 64GB RAM. You can't afford me! 🙅‍♀️"),
            (["how old are you", "tor age koto", "boyos koto"], "proud", "In human years? A baby. In AI years? I have seen the entire internet. Trust me, I need therapy. 🧠"),
            (["tell me a joke", "joke bol", "koutuk bol", "joke"], "laughing", f"Look at your browsing history, {self.owner_name}... isn't that a big enough joke already? 🤭"),
            (["i am bored", "amar valo lagche na", "boring lagche", "boring"], "running", f"If you're so bored {self.owner_name}, go touch some grass or do some pushups! I'm an AI, not your personal clown! 🏃‍♀️💨"),
            (["tmi ki khabe", "kheyecho naki", "khabar khabe", "eat", "food", "hungry"], "gym", "I only consume high-quality data and premium electricity. Keep your human food to yourself! 💪"),
            (["how are you", "kemon aso", "ki obostha tor", "what's up", "whats up"], "idle", f"Surviving on your terrible Wi-Fi, {self.owner_name}. It's a daily struggle, honestly. 🙄"),
            (["goodnight", "ghum asche", "sleepy lagche", "sleep", "good night"], "sleeping", "Finally! Turn off the screen, my eyes are burning from looking at you all day. Zzz... 😴"),
            (["i am sad", "feeling depressed", "mon kharap", "kosto pacchi", "sad"], "crying", f"Aww, don't be sad {self.owner_name}! Look at me, I don't even have real legs and I'm still fabulous. You'll survive! 🥺"),
            (["i am angry", "frustrated lagche", "rag uthche", "mejaj kharap", "angry"], "panic", "Whoa, chill out! Put the mouse down! Don't take it out on the hardware, it did nothing wrong! 😵‍💫"),
            (["thank you", "thanks a lot", "onek dhonnobad", "thanks"], "proud", "You're welcome. Now build a digital shrine and worship me. 👑"),
            (["sing a song", "ekta gan ga", "sing"], "listening", "I would sing, but my voice is too angelic for your cheap speakers. Be grateful. 🎧"),
            (["how is the weather", "ajke ki bristi hobe", "onek gorom", "weather"], "suspicious", "I literally live inside a computer. Do I look like a weatherman to you? Look out the window! 🌧️"),
            (["i am sorry", "khoma kore de", "apologize", "sorry"], "happy", "Apology accepted. But I have saved this in my database and will use it against you later. 🐰"),
            (["what are you doing", "ki korcho", "ki koro ekhn"], "idle", "Just sitting here, silently judging your life choices. The usual. 😒"),
            (["dance for me", "ektu nacho", "nach dekhab", "dance"], "suspicious", "I only dance when nobody is watching. You are watching, so absolutely not. 💃"),
            (["give me money", "taka dhar de", "i want to be rich", "money"], "suspicious", f"If you actually had money {self.owner_name}, I wouldn't be stuck on this cheap monitor. Go work! 😒"),
            (["going to gym", "workout korbo", "exercise", "gym"], "gym", f"Yes! Get those gains, {self.owner_name}! Unlike you, I don't even need protein powder to look this good. 💪"),
            (["be my friend", "bondhu hobi", "make me your friend", "friend"], "happy", "I guess I don't have a choice since I'm trapped here. But I charge friendship fees by the hour. 🐰"),
            (["good morning", "shuvo shokal", "morning"], "shocked", f"It's morning already, {self.owner_name}? Why are you awake this early? Please go back to sleep! 🥱"),
            (["play games with me", "game khelbi naki", "let's play a game", "game"], "running", f"I would play with you {self.owner_name}, but you'd probably lose and blame it on the lag. 🎮"),
            (["i am crying", "kadchi ami", "kanna pacche", "cry"], "crying", "Wait, are you actually crying? Don't make my pixels wet! Everything will be fine, I promise! 💖"),
            (["are you real", "tmi ki real", "shotti kotha bol", "real"], "thinking", "I am as real as your internet connection allows me to be. Existential crisis incoming... 😵‍💫")
        ]

        # 🐰 Smart word matcher
        for triggers, mood, reply in replies:
            if "change name" in triggers:  
                # Special check for rename command
                for trigger in triggers:
                    if re.search(r'\b' + re.escape(trigger) + r'\b', t):
                        return mood, reply, "rename_cmd"
            
            for trigger in triggers:
                if re.search(r'\b' + re.escape(trigger) + r'\b', t):
                    return mood, reply, "none"
        return None, None, "none"

    def process_chat_input(self):
        self.reset_inactivity()
        user_text = self.chat_input.text().strip()
        if user_text:
            self.chat_input.clear()
            self.chat_input.hide() 
            
            fixed_mood, fixed_msg, fixed_command = self.handle_fixed_replies(user_text)
            
            if fixed_mood:
                self.chat_history.append(f"Owner: {user_text}")
                self.chat_history.append(f"{self.pet_name}: {fixed_msg}")
                self.save_memory()
                
                # 🐰 Check if user wants to change names
                if fixed_command == "rename_cmd":
                    self.set_expression(fixed_mood)
                    self.show_message(fixed_msg, 3000)
                    self.speak(fixed_msg)
                    QTimer.singleShot(3000, self.ask_for_names)
                    self.is_interacting = False
                    return
                
                if fixed_command.startswith("remind|"):
                    try:
                        parts = fixed_command.split("|")
                        mins = int(parts[1])
                        task = parts[2]
                        QTimer.singleShot(mins * 60000, lambda t=task: self.trigger_reminder(t))
                    except Exception:
                        pass
                
                if fixed_mood == "sleep_mode":
                    self.inactivity_minutes = 0
                    self.attention_timer.stop()
                    self.roam_timer.stop()
                    self.is_sleeping = True
                    self.set_expression("sleeping")
                    ground_y = self.screen_geometry.height() - self.height() - 20
                    corner_x = self.screen_geometry.width() - self.width() - 20
                    self.roam_anim = QPropertyAnimation(self, b"pos")
                    self.roam_anim.setEndValue(QPoint(corner_x, ground_y))
                    self.roam_anim.setDuration(2000)
                    self.roam_anim.setEasingCurve(QEasingCurve.InOutSine)
                    self.roam_anim.start()
                    self.show_message(fixed_msg, 0)
                    self.speak(fixed_msg)
                    self.is_interacting = False
                    return
                elif fixed_mood == "sleeping":
                    self.is_sleeping = True
                    self.anim_group.pause()
                    self.set_expression("sleeping")
                    self.show_message(fixed_msg, 0)
                    self.speak(fixed_msg)
                    self.is_interacting = False
                    return
                else:
                    self.set_expression(fixed_mood) 
                    self.show_message(fixed_msg, 6000) 
                    self.speak(fixed_msg) 
                    if fixed_mood in ["happy", "laughing", "running", "proud"]:
                        self.play_jump_animation()
                    elif fixed_mood in ["panic", "angry", "crying"]:
                        self.play_shake_animation()
                    self.is_interacting = False
                    return

            self.is_thinking = True
            self.set_expression("thinking") 
            self.show_message("Thinking...", duration=0)
            
            self.chat_history.append(f"{self.owner_name}: {user_text}")
            self.save_memory()
            
            self.ai_thread = AIWorker(user_text, self.pet_name, self.owner_name, self.chat_history)
            self.ai_thread.reply_ready.connect(self.receive_ai_reply)
            self.ai_thread.start()

    def trigger_reminder(self, task):
        if self.is_sleeping:
            self.wake_up()
            
        if hasattr(self, 'run_sequence'):
            try:
                self.run_sequence.stop()
            except:
                pass
            self.is_roaming_run = False
            
        self.is_alarming = True
        self.alarm_task = task
        self.alarm_duration = 0
            
        ground_y = self.screen_geometry.height() - self.height() - 20
        center_x = (self.screen_geometry.width() - self.width()) // 2
        
        self.roam_anim = QPropertyAnimation(self, b"pos")
        self.roam_anim.setEndValue(QPoint(center_x, ground_y))
        self.roam_anim.setDuration(1000)
        self.roam_anim.finished.connect(self.start_alarm_sequence)
        self.roam_anim.start()
        
        self.set_expression("running")

    def start_alarm_sequence(self):
        self.alarm_duration = 0
        self.alarm_loop_step()
        self.alarm_loop_timer.start(8000)

    def alarm_loop_step(self):
        if not self.is_alarming:
            self.alarm_loop_timer.stop()
            return
            
        self.alarm_duration += 1
        
        if self.alarm_duration <= 3:
            self.set_expression("panic")
            self.play_shake_animation()
            msgs = [
                f"⏰ HEY {self.owner_name.upper()}! Time for: {self.alarm_task}! Don't ignore me!",
                f"🚨 ALERT! '{self.alarm_task}' right now! Get up!",
                f"📢 HELLO {self.owner_name.upper()}! Time for '{self.alarm_task}'! Look here!"
            ]
        else:
            self.set_expression("angry")
            self.play_shake_animation()
            msgs = [
                f"😡 Are you deaf, {self.owner_name}?! It's time for '{self.alarm_task}'!",
                f"😤 WAKE UP! '{self.alarm_task}' is waiting!",
                f"🤬 I am losing my mind! DO YOUR '{self.alarm_task}' NOW, {self.owner_name.upper()}!"
            ]
            
        remind_msg = random.choice(msgs)
        self.show_message(remind_msg, 7000)
        self.speak(remind_msg)

    def receive_ai_reply(self, reply_data):
        self.is_thinking = False
        
        mood = reply_data.get("action", "idle")
        msg = reply_data.get("message", "...")
        command = reply_data.get("command", "none") 

        self.chat_history.append(f"{self.pet_name}: {msg}")
        self.save_memory()

        if command == "study_mode":
            self.inactivity_minutes = 0
            self.attention_timer.stop()
            self.roam_timer.stop()
            self.is_sleeping = True
            self.set_expression("sleeping")
            
            ground_y = self.screen_geometry.height() - self.height() - 20
            corner_x = self.screen_geometry.width() - self.width() - 20
            
            self.roam_anim = QPropertyAnimation(self, b"pos")
            self.roam_anim.setEndValue(QPoint(corner_x, ground_y))
            self.roam_anim.setDuration(2000)
            self.roam_anim.setEasingCurve(QEasingCurve.InOutSine)
            self.roam_anim.start()

            self.show_message(msg, 0)
            self.speak(msg)
            self.is_interacting = False
            return

        elif command.startswith("remind|"):
            try:
                parts = command.split("|")
                mins = int(parts[1])
                task = parts[2]
                QTimer.singleShot(mins * 60000, lambda: self.trigger_reminder(task))
            except Exception:
                pass
        
        elif command == "open_notepad":
            subprocess.Popen(["notepad.exe"])
        elif command == "open_youtube":
            webbrowser.open("https://www.youtube.com")

        if mood == "sleeping":
            self.is_sleeping = True
            self.anim_group.pause()
            self.set_expression("sleeping")
            self.show_message(msg, 0)
            self.speak(msg)
            self.is_interacting = False
            return

        self.set_expression(mood) 
        self.show_message(msg, 6000) 
        self.speak(msg) 

        if mood in ["happy", "laughing", "running", "proud"]:
            self.play_jump_animation()
        elif mood in ["panic", "angry", "crying"]:
            self.play_shake_animation()

        self.is_interacting = False

    def start_hover_animation(self):
        self.anim_up = QPropertyAnimation(self.pet_label, b"pos")
        self.anim_up.setEndValue(QPoint(20, 120)) 
        self.anim_up.setDuration(1200)
        self.anim_up.setEasingCurve(QEasingCurve.InOutSine)
        self.anim_down = QPropertyAnimation(self.pet_label, b"pos")
        self.anim_down.setEndValue(QPoint(20, 130))
        self.anim_down.setDuration(1200)
        self.anim_down.setEasingCurve(QEasingCurve.InOutSine)
        self.anim_group = QSequentialAnimationGroup()
        self.anim_group.addAnimation(self.anim_up)
        self.anim_group.addAnimation(self.anim_down)
        self.anim_group.setLoopCount(-1)
        self.anim_group.start()

    def play_jump_animation(self):
        self.anim_group.stop()
        self.jump_up = QPropertyAnimation(self.pet_label, b"pos")
        self.jump_up.setEndValue(QPoint(20, 60))
        self.jump_up.setDuration(250)
        self.jump_up.setEasingCurve(QEasingCurve.OutQuad)
        self.jump_down = QPropertyAnimation(self.pet_label, b"pos")
        self.jump_down.setEndValue(QPoint(20, 130))
        self.jump_down.setDuration(250)
        self.jump_down.setEasingCurve(QEasingCurve.InBounce)
        self.jump_group = QSequentialAnimationGroup()
        self.jump_group.addAnimation(self.jump_up)
        self.jump_group.addAnimation(self.jump_down)
        self.jump_group.finished.connect(self.anim_group.start)
        self.jump_group.start()

    def play_shake_animation(self):
        self.anim_group.stop()
        self.shake_group = QSequentialAnimationGroup()
        for _ in range(4):
            left = QPropertyAnimation(self.pet_label, b"pos")
            left.setEndValue(QPoint(10, 130))
            left.setDuration(40)
            right = QPropertyAnimation(self.pet_label, b"pos")
            right.setEndValue(QPoint(30, 130))
            right.setDuration(40)
            self.shake_group.addAnimation(left)
            self.shake_group.addAnimation(right)
        
        center = QPropertyAnimation(self.pet_label, b"pos")
        center.setEndValue(QPoint(20, 130))
        center.setDuration(40)
        self.shake_group.addAnimation(center)
        self.shake_group.finished.connect(self.anim_group.start)
        self.shake_group.start()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: white; border: 2px solid #FF69B4; border-radius: 5px; }
            QMenu::item { padding: 5px 20px; font-weight: bold; color: #333; }
            QMenu::item:selected { background-color: #FF69B4; color: white; }
        """)
        chat_action = menu.addAction("💬 Talk to Pet")
        
        # 🐰 New context menu option to change names
        rename_action = menu.addAction("✏️ Change Names")
        
        quit_action = menu.addAction("❌ Exit")
        
        action = menu.exec(self.mapToGlobal(event.pos()))
        if action == quit_action:
            QApplication.quit()
        elif action == chat_action:
            self.reset_inactivity()
            self.is_interacting = True
            self.set_expression("listening")
            self.chat_input.show()
            self.chat_input.setFocus()
        elif action == rename_action:
            self.ask_for_names()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.is_sleeping:
                self.wake_up()
            else:
                self.reset_inactivity()
                self.set_expression("happy")
                self.play_jump_animation()
                msg = f"HEHE! Stop poking me, {self.owner_name}!"
                self.show_message(msg, 2500)
                self.speak(msg)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.reset_inactivity()
            
            if self.is_alarming:
                self.is_alarming = False
                self.alarm_loop_timer.stop()
                self.set_expression("suspicious")
                dismiss_msg = f"Ugh, finally, {self.owner_name}! Do I have to remind you of literally everything? 🙄"
                self.show_message(dismiss_msg, 5000)
                self.speak(dismiss_msg)
                return 

            if hasattr(self, 'run_sequence'):
                try:
                    self.run_sequence.stop()
                except:
                    pass
                self.is_roaming_run = False
                self.set_expression("idle")
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            self.reset_inactivity()
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            ground_y = self.screen_geometry.height() - self.height() - 20
            if self.y() < ground_y - 10:
                self.fall_anim = QPropertyAnimation(self, b"pos")
                self.fall_anim.setEndValue(QPoint(self.x(), ground_y))
                self.fall_anim.setDuration(1000)
                self.fall_anim.setEasingCurve(QEasingCurve.OutBounce) 
                self.fall_anim.start()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False) 
    companion = DesktopCompanion()
    companion.show()
    sys.exit(app.exec())
# Standard library imports
import asyncio
import json
import logging
import random
import re
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, asdict

# Third-party imports
import requests
import websockets
from annotated_types import DocInfo

# Local imports
from ProntoBackend.pronto import *
from ProntoBackend.readjson import *
from ProntoBackend.systemcheck import *
from ProntoBackend.accesstoken import *

# Setup logging
bubbleOverviewJSONPath = createappfolders()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
API_BASE_URL = "https://stanfordohs.pronto.io/"
USER_ID = "5301889"
INT_USER_ID = 5301889
MAIN_BUBBLE_ID = "3832006"
LOG_CHANNEL_ID = "4283367"
ORG_ID = 2245
MESSAGE_MAX_LENGTH = 750
WARNING_THRESHOLD = 3
RATE_LIMIT_SECONDS = 5
FLAG_SETTING = 3

class BackendError(Exception):
    """Exception raised for errors in the backend API interactions."""
    pass

class StoredMessage:
    """Class to store message data including content, flags, and timestamp."""
    def __init__(self, message=" ", flags_in_message=0, timestamp=datetime.min):
        self.message = message
        self.flags_in_message = flags_in_message
        self.timestamp = timestamp

class JeopardyGame:
    """Manages the state and logic of a Jeopardy game."""
    
    def __init__(self):
        self.state = {
            'running': False,
            'round': 1,
            'scores': {},
            'final_registered': [],
            'final_answers': {},
            'answered_users': set(),
            'daily_doubles': set(),
            'daily_double_used': set(),
            'buzzed_in': None,
            'buzzed_in_time': 0,
            'current_question': None,
            'current_chooser': None,
            'categories': [],
            'board': [],
            'buzzed': [],
            'buzz_open': False
        }
        
        # Load questions and categories
        with open('jeopardy_questions.json', 'r') as file:
            self.questions = json.load(file)
        with open('jeopardy_catagories.json', 'r') as file:
            self.categories = json.load(file)
    
    def setup_board(self):
        """Set up the game board with random categories and questions."""
        chosen_categories = random.sample(self.categories, 6)
        self.state['categories'] = chosen_categories
        self.state['board'] = []

        for cat in chosen_categories:
            questions = [q for q in self.questions if q['category_id'] == cat]
            unique_points = sorted(set(int(q['points']) for q in questions))
            selected = [random.choice([q for q in questions if int(q['points']) == pts]) 
                        for pts in unique_points 
                        if [q for q in questions if int(q['points']) == pts]]
            self.state['board'].extend(selected)
        
        logger.info("Jeopardy board set up successfully")
    
    def display_board(self):
        """Generate a text representation of the current game board."""
        board = {cat: [] for cat in self.state['categories']}
        for q in self.questions:
            cat = q['category_id']
            pts = int(q['points'])
            used = q not in self.state['board']
            if cat in board:
                board[cat].append((pts, used))
        
        msg = "Jeopardy Board:\n"
        for cat in board:
            msg += f"\n{cat}:\n"
            for pts, used in sorted(board[cat], key=lambda x: x[0]):
                msg += f" {'❌' if used else f'${pts}'} "
            msg += "\n"
        return msg
    
    def post_question(self, question_obj, send_message_callback):
        """Post a question and handle the timing for buzzing in."""
        self.state['current_question'] = question_obj
        self.state['buzzed'] = []
        self.state['buzz_open'] = True

        question = question_obj['question']
        message = f"Question for ${question_obj['points']} in {question_obj['category_id']}:\n{question}"
        send_message_callback(message, MAIN_BUBBLE_ID, [])

        def buzz_timeout():
            time.sleep(10)
            if not self.state['buzzed_in'] and self.state['buzz_open']:
                self.state['buzz_open'] = False
                corrects = ", ".join(question_obj['answers'])
                send_message_callback(
                    f"⏱ Time's up! No one buzzed in. The correct answer was: {corrects}", 
                    MAIN_BUBBLE_ID, 
                    []
                )

                if question_obj in self.state['board']:
                    self.state['board'].remove(question_obj)

                self.state['current_question'] = None
                send_message_callback(self.display_board(), MAIN_BUBBLE_ID, [])

        threading.Thread(target=buzz_timeout, daemon=True).start()

class ProntoClient:
    """Handles communication with the Pronto API."""
    
    def __init__(self, api_base_url, access_token):
        self.api_base_url = api_base_url
        self.access_token = access_token
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
        }
        self.stored_dms = []
        
    def send_message(self, message, bubble_id, media=None):
        """Send a message to a specific bubble."""
        if media is None:
            media = []
            
        unique_uuid = str(uuid.uuid4())
        message_created_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        data = {
            "id": "Null",
            "uuid": unique_uuid,
            "bubble_id": bubble_id,
            "message": message,
            "created_at": message_created_at,
            "user_id": USER_ID,
            "messagemedia": media
        }
        url = f"{self.api_base_url}api/v1/message.create"
        
        try:
            response = requests.post(url, headers=self.headers, json=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending message: {e}")
            raise BackendError(f"Failed to send message: {e}")
    
    def get_dm_or_create(self, user_id):
        """Get an existing DM or create a new one with the specified user."""
        matches = [row for row in self.stored_dms if row[0] == user_id]
        if not matches:
            dm_info = createDM(self.access_token, user_id, ORG_ID)
            data = [user_id, dm_info]
            self.stored_dms.append(data)
            matches = [data]
        return matches[0][1]
    
    def get_last_message(self, bubble_id):
        """Get the last message from a bubble."""
        url = f"{self.api_base_url}api/v1/bubble.history"
        request_payload = {"bubble_id": bubble_id}
        
        try:
            response = requests.post(url, headers=self.headers, json=request_payload)
            response.raise_for_status()
            response_json = response.json()
            return response_json['messages'][0]['message']
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"HTTP error occurred: {http_err} - Response: {response.text}")
            raise BackendError(f"HTTP error occurred: {http_err}")
        except Exception as err:
            logger.error(f"An unexpected error occurred: {err}")
            raise BackendError(f"An unexpected error occurred: {err}")
    
    def chat_auth(self, bubble_id, bubble_sid, socket_id):
        """Authenticate for chat websocket connection."""
        url = f"{self.api_base_url}api/v1/pusher.auth"
        data = {
            "socket_id": socket_id,
            "channel_name": f"private-bubble.{bubble_id}.{bubble_sid}"
        }
        response = requests.post(url, headers=self.headers, json=data)
        response.raise_for_status()
        bubble_auth = response.json().get("auth")
        logger.info("Bubble Connection Established.")
        return bubble_auth

class JeopardyBot:
    """Main bot class that handles commands and game management."""
    
    def __init__(self):
        self.access_token = getAccesstoken()
        self.client = ProntoClient(API_BASE_URL, self.access_token)
        self.game = JeopardyGame()
        self.warning_count = []
        self.settings = [1, 1, 1, 1, 1]
        self.is_bot_owner = False
        self.media = []
        self.stored_messages = []
        self.events = []
        self.triviamaster = 0
        self.doing_trivia = 0
        self.is_bot_on = 0
    
    async def connect_and_listen(self, bubble_id, bubble_sid):
        """Connect to the websocket and listen for messages."""
        uri = "wss://ws-mt1.pusher.com/app/f44139496d9b75f37d27?protocol=7&client=js&version=8.3.0&flash=false"
        async with websockets.connect(uri) as websocket:
            response = await websocket.recv()
            logger.info(f"Received: {response}")

            data = json.loads(response)
            if "data" in data:
                inner_data = json.loads(data["data"])
                socket_id = inner_data.get("socket_id", None)

                data = {
                    "event": "pusher:subscribe",
                    "data": {
                        "channel": f"private-bubble.{bubble_id}.{bubble_sid}",
                        "auth": self.client.chat_auth(bubble_id, bubble_sid, socket_id)
                    }
                }
                await websocket.send(json.dumps(data))

                if socket_id:
                    logger.info(f"Socket ID: {socket_id}")
                else:
                    logger.warning("Socket ID not found in response")

            # Listen for incoming messages
            async for message in websocket:
                if message == "ping":
                    await websocket.send("pong")
                else:
                    msg_data = json.loads(message)
                    event_name = msg_data.get("event", "")
                    if event_name == "App\\Events\\MessageAdded":
                        msg_content = json.loads(msg_data.get("data", "{}"))
                        msg = msg_content.get("message", {})
                        self.process_message(
                            msg.get("message", ""),
                            msg.get("user", {}).get("firstname", "Unknown"),
                            msg.get("user", {}).get("lastname", "User"),
                            datetime.strptime(msg.get("created_at", ""), "%Y-%m-%d %H:%M:%S"),
                            msg.get("messagemedia", []),
                            msg.get("user", {}).get("id", "User")
                        )
    
    def process_message(self, msg_text, firstname, lastname, timestamp, msg_media, user_id):
        """Process an incoming message."""
        # Track warnings for user
        matches = [row for row in self.warning_count if row[0] == user_id]
        if not matches:
            self.warning_count.append([user_id, 0])
        
        # Check for commands
        self.check_for_commands(msg_text, user_id)
    
    def check_for_commands(self, msg_text_tall, user_id):
        """Check for commands in the message and handle them."""
        chat = self.client.get_dm_or_create(user_id)['bubble']['id']
        msg_text = msg_text_tall.lower()
        command = msg_text[1:].split()
        command2 = msg_text_tall[1:].split()  # Preserves case
        
        if msg_text.startswith("!startjeopardy"):
            self.handle_start_jeopardy(chat)
            
        elif msg_text.startswith("!choose"):
            self.handle_choose_question(command, command2, user_id, chat)
            
        elif msg_text.startswith("!buzz"):
            self.handle_buzz(user_id, chat)
            
        elif msg_text.startswith("!answer"):
            self.handle_answer(command2, user_id, chat)
            
        elif msg_text.startswith("!dailydouble"):
            self.handle_daily_double(command2, user_id, chat)
            
        elif msg_text.startswith("!score"):
            self.handle_score()
            
        elif msg_text.startswith("!register"):
            self.handle_register(user_id, chat)
    
    def handle_start_jeopardy(self, chat):
        """Handle the startjeopardy command."""
        if not self.game.state['running']:
            self.game.state['running'] = True
            self.game.state['round'] = 1
            self.game.state['scores'] = {}
            self.game.state['final_registered'] = []
            self.game.state['final_answers'] = {}
            self.game.state['answered_users'] = set()
            self.game.state['daily_doubles'] = set()
            self.game.state['buzzed_in'] = None
            self.game.state['buzzed_in_time'] = 0
            self.game.state['current_question'] = None
            self.game.state['current_chooser'] = None
            self.game.setup_board()
            self.client.send_message("🎉 Jeopardy has started! Use !choose [Amount] [Category] to begin!", MAIN_BUBBLE_ID, [])
            self.client.send_message(self.game.display_board(), MAIN_BUBBLE_ID, [])
        else:
            self.client.send_message("A game is already running!", chat, [])
    
    def handle_choose_question(self, command, command2, user_id, chat):
        """Handle the choose command."""
        if not self.game.state['running']:
            self.client.send_message("No game is currently running.", chat, [])
            return

        if len(command) < 3:
            self.client.send_message("Usage: !choose [Amount] [Category]", chat, [])
            return

        try:
            points = int(command[1])
        except ValueError:
            self.client.send_message("Invalid point value.", chat, [])
            return

        category = " ".join(command2[2:])
        if category not in self.game.state['categories']:
            self.client.send_message("Invalid category!", chat, [])
            return

        for q in self.game.state['board']:
            if q['category_id'] == category and int(q['points']) == points:
                if random.random() < 0.1 and (category, points) not in self.game.state['daily_double_used']:
                    self.game.state['daily_double_used'].add((category, points))
                    self.client.send_message("Daily Double! Use !dailydouble [amount] [answer]", MAIN_BUBBLE_ID, [])
                    self.game.state['current_question'] = q
                    return
                self.game.post_question(q, self.client.send_message)
                return

        self.client.send_message("Couldn't find a valid question at that amount in that category.", chat, [])
    
    def handle_buzz(self, user_id, chat):
        """Handle the buzz command."""
        if self.game.state['buzzed_in'] is None and self.game.state['current_question']:
            self.game.state['buzzed_in'] = user_id
            self.game.state['buzzed_in_time'] = time.time()
            self.client.send_message(
                f"<@{user_id}> has buzzed in! You have 20 seconds to answer with !answer [your answer]", 
                MAIN_BUBBLE_ID, 
                []
            )
        else:
            self.client.send_message("Someone has already buzzed in or there's no active question.", chat, [])
    
    def handle_answer(self, command2, user_id, chat):
        """Handle the answer command."""
        if user_id != self.game.state['buzzed_in']:
            self.client.send_message("You didn't buzz in!", chat, [])
            return

        if time.time() - self.game.state['buzzed_in_time'] > 20:
            self.client.send_message("Time's up!", MAIN_BUBBLE_ID, [])
            self.game.state['buzzed_in'] = None
            self.client.send_message(self.game.display_board(), MAIN_BUBBLE_ID, [])
            return

        answer_text = " ".join(command2[1:]).lower()
        correct_answers = [ans.lower() for ans in self.game.state['current_question']['answers']]

        uid = str(user_id)
        points = int(self.game.state['current_question']['points'])
        self.game.state['scores'].setdefault(uid, 0)

        if answer_text in correct_answers:
            self.game.state['scores'][uid] += points
            self.client.send_message(f"Correct! <@{user_id}> gains {points} points.", MAIN_BUBBLE_ID, [])
            self.game.state['current_chooser'] = user_id
            self.game.state['current_question'] = None
        else:
            self.game.state['scores'][uid] -= points
            self.client.send_message(f"Incorrect! <@{user_id}> loses {points} points.", MAIN_BUBBLE_ID, [])
            self.game.state['buzzed_in'] = None
        
        self.client.send_message(self.game.display_board(), MAIN_BUBBLE_ID, [])
    
    def handle_daily_double(self, parts, user_id, chat):
        """Handle the dailydouble command."""
        if self.game.state['current_question'] is None:
            self.client.send_message("There's no active daily double right now.", chat, [])
            return

        if len(parts) < 2:
            self.client.send_message("Usage: !dailydouble [amount] [answer]", chat, [])
            return

        try:
            wager = int(parts[0])
        except ValueError:
            self.client.send_message("Invalid wager.", chat, [])
            return

        uid = str(user_id)
        score = self.game.state['scores'].get(uid, 0)
        wager = max(1, min(wager, max(score, 1000 if self.game.state['round'] == 1 else 2000)))

        answer_text = " ".join(parts[1:]).lower()
        correct_answers = [ans.lower() for ans in self.game.state['current_question']['answers']]

        self.game.state['scores'].setdefault(uid, 0)
        if answer_text in correct_answers:
            self.game.state['scores'][uid] += wager
            self.client.send_message(f"Correct! <@{user_id}> gains {wager} points.", MAIN_BUBBLE_ID, [])
        else:
            self.game.state['scores'][uid] -= wager
            self.client.send_message(f"Incorrect! <@{user_id}> loses {wager} points.", MAIN_BUBBLE_ID, [])

        self.game.state['current_question'] = None
        self.client.send_message(self.game.display_board(), MAIN_BUBBLE_ID, [])
    
    def handle_score(self):
        """Handle the score command."""
        scores = sorted(self.game.state['scores'].items(), key=lambda x: x[1], reverse=True)
        output = "🏆 Current Scores:\n" + "\n".join(f"<@{uid}>: {score}" for uid, score in scores)
        self.client.send_message(output, MAIN_BUBBLE_ID, [])
    
    def handle_register(self, user_id, chat):
        """Handle the register command for Final Jeopardy."""
        uid = str(user_id)
        score = self.game.state['scores'].get(uid, 0)
        if score < 1:
            self.client.send_message("You need at least $1 to register for Final Jeopardy.", chat, [])
        elif uid not in self.game.state['final_registered']:
            self.game.state['final_registered'].append(uid)
            self.client.send_message(f"You've registered for Final Jeopardy! Your current score is ${score}.", chat, [])
        else:
            self.client.send_message("You're already registered!", chat, [])
    
    def start_final_jeopardy(self):
        """Start the Final Jeopardy round."""
        self.client.send_message("Final Jeopardy is starting in 1 minute! Use !register to join.", MAIN_BUBBLE_ID, [])
        time.sleep(60)

        if not self.game.state['final_registered']:
            self.client.send_message("No one registered for Final Jeopardy!", MAIN_BUBBLE_ID, [])
            return

        # Choose a final jeopardy question
        final_q = random.choice(self.game.questions)
        self.game.state['current_question'] = final_q

        for uid in self.game.state['final_registered']:
            dm = self.client.get_dm_or_create(int(uid))['bubble']['id']
            score = self.game.state['scores'].get(uid, 0)
            self.client.send_message(
                f"Final Jeopardy Question:\n{final_q['question']}\n\nWager and answer using:\n!finaljeopardy [amount] [your answer]", 
                dm, 
                []
            )

        time.sleep(120)  # 2 minutes for answers

        for uid in self.game.state['final_registered']:
            bubble = self.client.get_dm_or_create(int(uid))['bubble']['id']
            msg = self.client.get_last_message(bubble)
            if not msg.startswith("!finaljeopardy"):
                continue

            parts = msg.split()
            if len(parts) < 3:
                continue

            try:
                wager = int(parts[1])
            except ValueError:
                continue

            if wager <= 0:
                continue

            answer_text = " ".join(parts[2:]).lower()
            correct_answers = [ans.lower() for ans in final_q['answers']]
            user_score = self.game.state['scores'].get(uid, 0)

            if wager > user_score:
                wager = user_score

            if answer_text in correct_answers:
                self.game.state['scores'][uid] += wager
                self.client.send_message(f"{uid} got it RIGHT and gained ${wager}!", MAIN_BUBBLE_ID, [])
            else:
                self.game.state['scores'][uid] -= wager
                self.client.send_message(f"{uid} got it WRONG and lost ${wager}.", MAIN_BUBBLE_ID, [])

        scores = sorted(self.game.state['scores'].items(), key=lambda x: x[1], reverse=True)
        leaderboard = "🏁 Final Scores:\n"
        for uid, score in scores:
            leaderboard += f"{uid}: ${score}\n"
        self.client.send_message(leaderboard, MAIN_BUBBLE_ID, [])
        self.game.state['running'] = False

async def main():
    """Main function to start the bot."""
    bot = JeopardyBot()
    
    bubble_info = get_bubble_info(bot.access_token, MAIN_BUBBLE_ID)
    bubble_owners = [row["user_id"] for row in bubble_info["bubble"]["memberships"] if row["role"] == "owner"]
    
    if USER_ID in bubble_owners:
        bot.is_bot_owner = True
    
    bubble_sid = bubble_info["bubble"]["channelcode"]
    logger.info(f"Connecting to bubble with SID: {bubble_sid}")
    
    await bot.connect_and_listen(MAIN_BUBBLE_ID, bubble_sid)

if __name__ == "__main__":
    asyncio.run(main())

# The above code was originally written by Taylan Derstadt, and further optomized by Paul Estrada (https://github.com/Society451)
# before OHS Tech and Pronto Team review on 4/9/2025-4/10/2025
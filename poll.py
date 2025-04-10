# Standard library imports
import asyncio
import json
import logging
import os
import random
import re
import sys
import time
import uuid
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict

# Third-party imports
import requests
import websockets
from aiohttp import web

# Local imports
from ProntoBackend.pronto import *
from ProntoBackend.readjson import *
from ProntoBackend.systemcheck import *
from ProntoBackend.accesstoken import *

# Setup logging
auth_path, chats_path, bubbles_path, loginTokenJSONPath, authTokenJSONPath, verificationCodeResponseJSONPath, settings_path, encryption_path, logs_path, settingsJSONPath, keysJSONPath, bubbleOverviewJSONPath, users_path = createappfolders()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
API_BASE_URL = "https://stanfordohs.pronto.io/"
USER_ID = "5301889"
INT_USER_ID = 5301889
MAIN_BUBBLE_ID = "4293718"
LOG_CHANNEL_ID = "4283367"
ORG_ID = 2245
MESSAGE_MAX_LENGTH = 750
WARNING_THRESHOLD = 3
RATE_LIMIT_SECONDS = 5
FLAG_SETTING = 3

# Trivia URLs
TRIVIA_URLS = {
    'arts': "https://raw.githubusercontent.com/el-cms/Open-trivia-database/refs/heads/master/en/todo/arts_and_literature.json",
    'entertainment': "https://raw.githubusercontent.com/el-cms/Open-trivia-database/refs/heads/master/en/todo/entertainment.json",
    'food': "https://raw.githubusercontent.com/el-cms/Open-trivia-database/refs/heads/master/en/todo/food_and_drink.json",
    'geography': "https://raw.githubusercontent.com/el-cms/Open-trivia-database/refs/heads/master/en/todo/geography.json",
    'history': "https://raw.githubusercontent.com/el-cms/Open-trivia-database/refs/heads/master/en/todo/history.json",
    'language': "https://raw.githubusercontent.com/el-cms/Open-trivia-database/refs/heads/master/en/todo/language.json",
    'mathematics': "https://raw.githubusercontent.com/el-cms/Open-trivia-database/refs/heads/master/en/todo/mathematics.json",
    'music': "https://raw.githubusercontent.com/el-cms/Open-trivia-database/refs/heads/master/en/todo/music.json",
    'people': "https://raw.githubusercontent.com/el-cms/Open-trivia-database/refs/heads/master/en/todo/people_and_places.json",
    'religion': "https://raw.githubusercontent.com/el-cms/Open-trivia-database/refs/heads/master/en/todo/religion_and_mythology.json",
    'science': "https://raw.githubusercontent.com/el-cms/Open-trivia-database/refs/heads/master/en/todo/science_and_nature.json",
    'sport': "https://raw.githubusercontent.com/el-cms/Open-trivia-database/refs/heads/master/en/todo/sport_and_leisure.json",
    'tech': "https://raw.githubusercontent.com/el-cms/Open-trivia-database/refs/heads/master/en/todo/tech_an_video_games.json",
    'toys': "https://raw.githubusercontent.com/el-cms/Open-trivia-database/refs/heads/master/en/todo/toys_and_games.json",
    'misc': "https://raw.githubusercontent.com/el-cms/Open-trivia-database/refs/heads/master/en/todo/uncategorized.json"
}

class BackendError(Exception):
    """Exception raised for errors in the backend API interactions."""
    pass

class StoredMessage:
    """Class to store message data including content, flags, and timestamp."""
    def __init__(self, message=" ", flags_in_message=0, timestamp=datetime.min):
        self.message = message
        self.flags_in_message = flags_in_message
        self.timestamp = timestamp

class TriviaManager:
    """Manages trivia games and questions."""
    
    def __init__(self):
        self.trivia_active = False
        self.trivia_master = None
        self.current_question = None
        self.trivia_categories = {}
        self.all_questions = []
        
    def load_trivia_data(self):
        """Load trivia data from URLs."""
        for category, url in TRIVIA_URLS.items():
            questions = self.download_questions(url)
            if questions:
                self.trivia_categories[category] = questions
                self.all_questions.extend(questions)
        
        logger.info(f"Loaded {len(self.all_questions)} trivia questions across {len(self.trivia_categories)} categories")
    
    def download_questions(self, url):
        """Download trivia questions from the given URL."""
        try:
            response = requests.get(url)
            if response.status_code == 200:
                text = response.text
                lines = text.split("\n")
                questions = []
                for line in lines:
                    if line.strip():
                        # Remove trailing comma if present
                        if line.endswith(','):
                            line = line[:-1]
                        try:
                            question_data = json.loads(line)
                            questions.append(question_data)
                        except json.JSONDecodeError:
                            pass
                return questions
            else:
                logger.error(f"Failed to download questions from {url}: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Error downloading questions from {url}: {e}")
            return []
    
    def start_trivia(self, user_id):
        """Start a new trivia game."""
        if not self.trivia_active:
            self.trivia_active = True
            self.trivia_master = user_id
            
            if not self.all_questions:
                self.load_trivia_data()
                
            if not self.all_questions:
                self.trivia_active = False
                return None, "Failed to load trivia questions"
                
            question_data = random.choice(self.all_questions)
            self.current_question = question_data
            return question_data['question'].capitalize(), None
        else:
            return None, "A trivia game is already active"
    
    def reveal_answer(self, user_id, bubble_owners):
        """Reveal the answer to the current trivia question."""
        if not self.trivia_active:
            return None, "No trivia game is currently active"
            
        if user_id != self.trivia_master and user_id not in bubble_owners:
            return None, "You don't have permission to reveal the answer"
            
        answers = self.current_question['answers']
        formatted_answers = ", ".join([answer.capitalize() for answer in answers])
        
        self.trivia_active = False
        self.trivia_master = None
        self.current_question = None
        
        return formatted_answers, None

class NumberGameManager:
    """Manages number guessing games."""
    
    def __init__(self):
        self.game_active = False
        self.correct_number = 0
        self.max_number = 0
        
    def start_game(self, max_num):
        """Start a new number guessing game."""
        if self.game_active:
            return False, "A game is already in progress"
            
        try:
            max_num = int(max_num)
        except ValueError:
            return False, "Invalid maximum number"
            
        if max_num < 1 or max_num > 10000:
            return False, "Maximum number must be between 1 and 10000"
            
        self.game_active = True
        self.max_number = max_num
        self.correct_number = random.randint(1, max_num)
        
        return True, f"I've chosen a number between 1 and {max_num}. Use !guess to make your guess!"
    
    def make_guess(self, guess):
        """Process a guess in the number game."""
        if not self.game_active:
            return False, "No number game is currently active"
            
        try:
            guess_num = int(guess)
        except ValueError:
            return False, "Invalid guess. Please enter a number"
            
        if guess_num < 1 or guess_num > self.max_number:
            return False, f"Your guess must be between 1 and {self.max_number}"
            
        if guess_num == self.correct_number:
            self.game_active = False
            return True, f"Correct! The answer was {guess_num}!"
        elif guess_num > self.correct_number:
            return False, f"{guess_num} is too high!"
        else:
            return False, f"{guess_num} is too low!"

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
        
    def chat_auth(self, bubble_id, bubble_sid, socket_id):
        """Authenticate for chat websocket connection."""
        url = f"{self.api_base_url}api/v1/pusher.auth"
        data = {
            "socket_id": socket_id,
            "channel_name": f"private-bubble.{bubble_id}.{bubble_sid}"
        }
        try:
            response = requests.post(url, headers=self.headers, json=data)
            response.raise_for_status()
            bubble_auth = response.json().get("auth")
            logger.info("Bubble Connection Established.")
            return bubble_auth
        except Exception as e:
            logger.error(f"Error authenticating chat: {e}")
            raise BackendError(f"Failed to authenticate chat: {e}")
            
    def upload_file_and_get_key(self, file_path, filename):
        """Upload a file to Pronto and get the file key."""
        url = "https://api.pronto.io/api/files"
        try:
            # Open the file and prepare headers
            with open(file_path, 'rb') as file:
                file_content = file.read()
                
            headers = {
                "Accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
                "Content-Length": str(len(file_content)),
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": "application/octet-stream"
            }

            # Send the PUT request
            response = requests.put(url, headers=headers, data=file_content)
            
            # Check if the request was successful
            if response.status_code == 200:
                response_data = response.json()
                file_key = response_data["data"]["key"]
                return file_key
            else:
                logger.error(f"Failed to upload file: {response.status_code}, {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error uploading file: {e}")
            return None

class PollBot:
    """Main bot class for managing polls, games and commands."""
    
    def __init__(self):
        self.access_token = getAccesstoken()
        self.client = ProntoClient(API_BASE_URL, self.access_token)
        self.trivia = TriviaManager()
        self.number_game = NumberGameManager()
        
        self.warning_count = []
        self.settings = [1, 1, 1, 1, 1]
        self.banished = []
        self.is_bot_owner = False
        self.bubble_owners = []
        
        self.process_messages = True
        self.last_activity_time = datetime.min
        self.stored_messages = []
        self.events = []
        
        # Rules lists
        self.adminrules = []
        self.rules = []
        
        if MAIN_BUBBLE_ID == "3832006":
            self.adminrules.append("https://docs.google.com/document/d/1pYLhxWIXCVS49JT3aBVMjMlXQmPQbxkgjQjEXj87dSA/edit?tab=t.0")
            self.rules.append("https://docs.google.com/document/d/17PhM0JfKHGlqzJ0OBohS4GQEAuc-ea0accY-lGU6zzs/edit?usp=sharing")
    
    def is_seven_digit_number(self, s):
        """Check if a string is a seven-digit number."""
        return bool(re.match(r'^\d{7}$', s))
    
    def check_if_valid_bubble(self, bubble_id):
        """Check if a bubble ID is valid."""
        # Could add validation logic here
        return True
    
    async def connect_and_listen(self, bubble_id, bubble_sid):
        """Connect to the websocket and listen for messages."""
        uri = "wss://ws-mt1.pusher.com/app/f44139496d9b75f37d27?protocol=7&client=js&version=8.3.0&flash=false"
        try:
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
                        try:
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
                        except Exception as e:
                            logger.error(f"Error processing message: {e}")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            self.client.send_message("There was an error with the bot connection. Attempting to reconnect...", MAIN_BUBBLE_ID, [])
            # Allow the main loop to handle reconnection
    
    def process_message(self, msg_text, user_firstname, user_lastname, timestamp, msg_media, user_id):
        """Process an incoming message."""
        # Check for bot toggling command
        if msg_text.startswith("!bot"):
            command = msg_text[1:].split()
            if len(command) > 1 and (user_id in self.bubble_owners or user_id == INT_USER_ID):
                if command[1] == "on":
                    self.process_messages = True
                    logger.info(f"Bot enabled by {user_id}")
                elif command[1] == "off":
                    self.process_messages = False
                    logger.info(f"Bot disabled by {user_id}")
        
        if not self.process_messages:
            return
            
        if user_id not in self.banished or user_id == INT_USER_ID:
            # Track warnings for user
            matches = [row for row in self.warning_count if row[0] == user_id]
            if not matches:
                self.warning_count.append([user_id, 0])
            
            # Check for commands
            self.check_for_commands(msg_text, user_id, msg_media)
    
    def check_for_commands(self, msg_text_tall, user_id, media=None):
        """Check for commands in the message and handle them."""
        if media is None:
            media = []
            
        chat = self.client.get_dm_or_create(user_id)['bubble']['id']
        msg_text = msg_text_tall.lower()
        command = msg_text[1:].split()
        command2 = msg_text_tall[1:].split()  # Preserves case
        
        # Allow time between commands to prevent spam
        current_time = datetime.now()
        time_since_last = current_time - self.last_activity_time
        cooldown_expired = time_since_last >= timedelta(seconds=5)
        
        # Moderation commands
        if msg_text.startswith("!banish") and (user_id in self.bubble_owners or user_id == INT_USER_ID):
            target_match = re.search(r"<@(\d+)>", command[1])
            if target_match:
                target_user = int(target_match.group(1))
                self.banished.append(target_user)
                logger.info(f"User {target_user} banished by {user_id}")
                self.client.send_message(f"User <@{target_user}> has been banished.", chat, [])
        
        elif msg_text.startswith("!unbanish") and (user_id in self.bubble_owners or user_id == INT_USER_ID):
            target_match = re.search(r"<@(\d+)>", command[1])
            if target_match:
                target_user = int(target_match.group(1))
                if target_user in self.banished:
                    self.banished.remove(target_user)
                    logger.info(f"User {target_user} unbanished by {user_id}")
                    self.client.send_message(f"User <@{target_user}> has been unbanished.", chat, [])
                else:
                    self.client.send_message(f"User <@{target_user}> is not banished.", chat, [])
        
        # Dice roll command
        elif msg_text.startswith("!roll") and cooldown_expired:
            self.last_activity_time = current_time
            if len(command) == 2:
                match = re.fullmatch(r'(\d+)d(\d+)', command[1])
                if match:
                    num_dice, sides = map(int, match.groups())
                    # Easter egg for the bot owner
                    if user_id == USER_ID and num_dice == 1 and sides == 500:
                        self.client.send_message("Rolling... 500 = 500", MAIN_BUBBLE_ID, media)
                        return

                    if num_dice < 1 or sides < 1:
                        self.client.send_message("Invalid input. Number of dice and sides must be greater than 0.", chat, media)
                        return
                    if num_dice > 500 or sides > 1000000:
                        self.client.send_message("Invalid input. Number of dice must be less than 500 and sides must be less than 1000000.", chat, media)
                        return
                        
                    rolls = [random.randint(1, sides) for _ in range(num_dice)]
                    total = sum(rolls)
                    rolls_str = " + ".join(map(str, rolls))
                    message = f"Rolling... {rolls_str} = {total}"
                    
                    # Send to DM if the message is too long
                    if len(message) > 500:
                        self.client.send_message(message, chat, media)
                    else:
                        self.client.send_message(message, MAIN_BUBBLE_ID, media)
                else:
                    self.client.send_message("Invalid format. Use !roll NdM (e.g., !roll 2d6)", chat, media)
            else:
                self.client.send_message("Invalid format. Use !roll NdM (e.g., !roll 2d6)", chat, media)
        
        # Coin flip command
        elif msg_text.startswith("!flip") and cooldown_expired:
            self.last_activity_time = current_time
            flip = random.choice(["Heads", "Tails"])
            self.client.send_message(f"I got... {flip}!", MAIN_BUBBLE_ID, media)
        
        # Trivia commands
        elif msg_text.startswith("!trivia") and cooldown_expired:
            self.last_activity_time = current_time
            question, error = self.trivia.start_trivia(user_id)
            if question:
                self.client.send_message(f"Question: {question}", MAIN_BUBBLE_ID, media)
            else:
                self.client.send_message(error, chat, media)
                
        elif msg_text.startswith("!reveal") and cooldown_expired:
            self.last_activity_time = current_time
            answers, error = self.trivia.reveal_answer(user_id, self.bubble_owners)
            if answers:
                self.client.send_message(f"Answer(s): {answers}", MAIN_BUBBLE_ID, media)
            else:
                self.client.send_message(error, chat, media)
        
        # Number game commands
        elif msg_text.startswith("!numbergame") and cooldown_expired:
            self.last_activity_time = current_time
            if len(command) == 2:
                success, message = self.number_game.start_game(command[1])
                if success:
                    self.client.send_message("Ok! I have chosen my number. Use !guess N to guess.", MAIN_BUBBLE_ID, [])
                else:
                    self.client.send_message(message, chat, media)
            else:
                self.client.send_message("Invalid format. Use !numbergame M (e.g., !numbergame 212)", chat, media)
                
        elif msg_text.startswith("!guess") and cooldown_expired:
            self.last_activity_time = current_time
            if len(command) == 2:
                success, message = self.number_game.make_guess(command[1])
                self.client.send_message(message, MAIN_BUBBLE_ID, media)
            else:
                self.client.send_message("Invalid format. Use !guess N (e.g., !guess 212)", chat, media)

async def handle_status(request):
    """Handler for the status endpoint."""
    return web.Response(text="Bot is running!", status=200)

async def main_loop():
    """Main loop for running the bot and web server."""
    # Create an aiohttp web application
    app = web.Application()
    app.router.add_get("/", handle_status)  # Add a route to check status

    # Get the PORT from environment variables or default to 8080
    port = int(os.getenv("PORT", "8080"))

    # Create and initialize the bot
    bot = PollBot()
    
    # Get bubble info and owners
    bubble_info = get_bubble_info(bot.access_token, MAIN_BUBBLE_ID)
    bot.bubble_owners = [row["user_id"] for row in bubble_info["bubble"]["memberships"] if row["role"] == "owner"]
    
    if USER_ID in bot.bubble_owners:
        bot.is_bot_owner = True
    
    bubble_sid = bubble_info["bubble"]["channelcode"]
    logger.info(f"Connecting to bubble with SID: {bubble_sid}")

    # Start the aiohttp server
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    logger.info(f"HTTP server running on port {port}")
    await site.start()

    # Run the WebSocket logic with automatic reconnection
    while True:
        try:
            await bot.connect_and_listen(MAIN_BUBBLE_ID, bubble_sid)
        except Exception as e:
            logger.error(f"Connection error: {e}")
            # Wait before reconnecting
            await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("Server stopped by user.")

# The above code was originally written by Taylan Derstadt, and further optomized by Paul Estrada (https://github.com/Society451)
# before OHS Tech and Pronto Team review on 4/9/2025-4/10/2025
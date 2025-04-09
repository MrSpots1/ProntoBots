from annotated_types import DocInfo
from networkx import trivial_graph
import websockets
import asyncio
from aiohttp import web
import json
import requests
import sys
import uuid
import re
from datetime import datetime, timezone
import time
import requests, logging
from datetime import datetime
from dataclasses import dataclass, asdict
from ProntoBackend.pronto import *
from ProntoBackend.readjson import *
from ProntoBackend.systemcheck import *
from ProntoBackend.accesstoken import *
import random
auth_path, chats_path, bubbles_path, loginTokenJSONPath, authTokenJSONPath, verificationCodeResponseJSONPath, settings_path, encryption_path, logs_path, settingsJSONPath, keysJSONPath, bubbleOverviewJSONPath, users_path = createappfolders()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
class BackendError(Exception):
    pass
class StoredMessage:
    def __init__(self, message=" ", flags_in_message=0, timestamp=datetime.min):
        self.message = message
        self.flags_in_message = flags_in_message
        self.timestamp = timestamp

random = random.Random()
# API Base URL and Credentials
api_base_url = "https://stanfordohs.pronto.io/"
accesstoken = ""
accesstoken = getAccesstoken()
global PROCESS_MESSAGES
PROCESS_MESSAGES = True
user_id = "5301889"
int_user_id = 5301889
main_bubble_ID = "4293718"
log_channel_ID = "4283367"
global media
media = []
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {accesstoken}",
}
global max_number
max_number = 0
global warning_count
warning_count = []
global settings
settings = [1, 1, 1, 1, 1]
global is_bot_owner
is_bot_owner = False
# Number of flagged sections in a message before a warning is issued
global flagsetting
flagsetting = 3
global jeopardy_questions
# Minimum number of seconds between messages from the same user before a warning is issued for rate limiting
global ratelimitseconds
ratelimitseconds = 5
global doing_guess_the_number
doing_guess_the_number = 0
global events 
events = []
global message_max_length
message_max_length = 750
global triviamaster
triviamaster = 0
# stanfordohs orginization id
global orgID
orgID = 2245
global correctnumber
correctnumber = 0
global doing_trivia
doing_trivia = 0
global is_bot_on
is_bot_on = 0
global warning_threshold
warning_threshold = 3
global stored_messages
stored_messages = []
warning_message = ""
log_message = ""
last_message_id = ""
global adminrules
adminrules = []
global rules
rules = []
if (main_bubble_ID == "3832006"):
    adminrules.append("https://docs.google.com/document/d/1pYLhxWIXCVS49JT3aBVMjMlXQmPQbxkgjQjEXj87dSA/edit?tab=t.0")
    rules.append("https://docs.google.com/document/d/17PhM0JfKHGlqzJ0OBohS4GQEAuc-ea0accY-lGU6zzs/edit?usp=sharing")
# Bad Words List URL
arts_url = "https://raw.githubusercontent.com/el-cms/Open-trivia-database/refs/heads/master/en/todo/arts_and_literature.json"
ent_url = "https://raw.githubusercontent.com/el-cms/Open-trivia-database/refs/heads/master/en/todo/entertainment.json"
food_url = "https://raw.githubusercontent.com/el-cms/Open-trivia-database/refs/heads/master/en/todo/food_and_drink.json"
geo_url = "https://raw.githubusercontent.com/el-cms/Open-trivia-database/refs/heads/master/en/todo/geography.json"
hist_url = "https://raw.githubusercontent.com/el-cms/Open-trivia-database/refs/heads/master/en/todo/history.json"
lang_url = "https://raw.githubusercontent.com/el-cms/Open-trivia-database/refs/heads/master/en/todo/language.json"
math_url = "https://raw.githubusercontent.com/el-cms/Open-trivia-database/refs/heads/master/en/todo/mathematics.json"
music_url = "https://raw.githubusercontent.com/el-cms/Open-trivia-database/refs/heads/master/en/todo/music.json"
people_url = "https://raw.githubusercontent.com/el-cms/Open-trivia-database/refs/heads/master/en/todo/people_and_places.json"
relg_url = "https://raw.githubusercontent.com/el-cms/Open-trivia-database/refs/heads/master/en/todo/religion_and_mythology.json"
sci_url = "https://raw.githubusercontent.com/el-cms/Open-trivia-database/refs/heads/master/en/todo/science_and_nature.json"
sport_url = "https://raw.githubusercontent.com/el-cms/Open-trivia-database/refs/heads/master/en/todo/sport_and_leisure.json"
tech_url = "https://raw.githubusercontent.com/el-cms/Open-trivia-database/refs/heads/master/en/todo/tech_an_video_games.json"
toys_url = "https://raw.githubusercontent.com/el-cms/Open-trivia-database/refs/heads/master/en/todo/toys_and_games.json"
misc_url = "https://raw.githubusercontent.com/el-cms/Open-trivia-database/refs/heads/master/en/todo/uncategorized.json"

async def listen_for_commands():
    global PROCESS_MESSAGES
    while True:
        command = input("Type 'on' to enable or 'off' to disable message processing: ").strip().lower()
        if command == "on":
            PROCESS_MESSAGES = True
            print("Message processing is enabled.")
        elif command == "off":
            PROCESS_MESSAGES = False
            print("Message processing is disabled.")
        else:
            print("Invalid command. Please type 'on' or 'off'.")

# Download Bad Words List
def download_wordlist(url):
    response = requests.get(url)
    if response.status_code == 200:
        words = response.text.split("\n")
        return set(word.strip().lower() for word in words if word.strip())
    else:
        print("Failed to download word list.")
        return set()

arts = list(download_wordlist(arts_url))
ent = list(download_wordlist(ent_url))
food = list(download_wordlist(food_url))
geo = list(download_wordlist(geo_url))
hist = list(download_wordlist(hist_url))
lang = list(download_wordlist(lang_url))
math = list(download_wordlist(math_url))
music = list(download_wordlist(music_url))
people = list(download_wordlist(people_url))
relg = list(download_wordlist(relg_url))
sci = list(download_wordlist(sci_url))
sport = list(download_wordlist(sport_url))
tech = list(download_wordlist(tech_url))
toys = list(download_wordlist(toys_url))
misc = list(download_wordlist(misc_url))
all_list = arts + ent + food + geo + hist + lang + math + music + people + relg + sci + sport + tech + toys + music


# Checks if a string is a 7 digit number
def is_seven_digit_number(s):
    return bool(re.match(r'^\d{7}$', s))


# Checks if a 7 digit string is a valid buble
def check_if_valid_bubble(imput):
    return True
    #add validation logic here with pronto api n stuff? should pass in a 7 digit number


# WebSocket and API Functions
def chat_auth(bubble_id, bubble_sid, socket_id):
    url = f"{api_base_url}api/v1/pusher.auth"
    data = {
        "socket_id": socket_id,
        "channel_name": f"private-bubble.{bubble_id}.{bubble_sid}"
    }
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
    bubble_auth = response.json().get("auth")
    print("Bubble Connection Established.")
    return bubble_auth

async def connect_and_listen(bubble_id, bubble_sid):
    uri = "wss://ws-mt1.pusher.com/app/f44139496d9b75f37d27?protocol=7&client=js&version=8.3.0&flash=false"
    async with websockets.connect(uri) as websocket:
        response = await websocket.recv()
        print(f"Received: {response}")

        data = json.loads(response)
        if "data" in data:
            inner_data = json.loads(data["data"])
            socket_id = inner_data.get("socket_id", None)

            data = {
                "event": "pusher:subscribe",
                "data": {
                    "channel": f"private-bubble.{bubble_id}.{bubble_sid}",
                    "auth": chat_auth(bubble_id, bubble_sid, socket_id)
                }
            }
            await websocket.send(json.dumps(data))

            if socket_id:
                print(f"Socket ID: {socket_id}")
            else:
                print("Socket ID not found in response")
        
        #add a check for owners changing to update the bubble_owners and is_bot_owner
        
        # Listen for incoming messages
        async for message in websocket:
            if message == "ping":
                await websocket.send("pong")
            else:
                msg_data = json.loads(message)
                event_name = msg_data.get("event", "")
                if event_name == "App\\Events\\MessageAdded":
                    msg_content = json.loads(msg_data.get("data", "{}"))
                    msg_text = msg_content.get("message", {}).get("message", "")
                    msg_user = msg_content.get("message", {}).get("user", {})
                    user_firstname = msg_user.get("firstname", "Unknown")
                    user_lastname = msg_user.get("lastname", "User")
                    user_id_websocket = msg_user.get("id", "User")
                    timestamp = msg_content.get("message", {}).get("created_at", "Unknown timestamp")
                    timestamp = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                    msg_media = msg_content.get("message", {}).get("messagemedia", [])

                    process_message(msg_text, user_firstname, user_lastname, timestamp, msg_media, user_id_websocket)


async def main(bubble_id, bubble_sid):
    while True:
        try:
            await connect_and_listen(bubble_id, bubble_sid)
        except Exception as e:
            print(e)
            send_message("Uhm yall there was an error, or the bots coming back online.", main_bubble_ID, [])
            pass
    """try:
        await connect_and_listen(bubble_id, bubble_sid)
    except Exception as e:
        print(e)"""



# Mod Bot Logic for Processing Messages
def process_message(msg_text, user_firstname, user_lastname, timestamp, msg_media, user_id_websocket):
    global PROCESS_MESSAGES
    if not PROCESS_MESSAGES:
        return

    matches = list(filter(lambda row: row[0] == user_id_websocket, warning_count))
    if matches.__len__() == 0:
        warning_count.append([user_id_websocket, 0])
        matches = list(filter(lambda row: row[0] == user_id_websocket, warning_count))
    msg_text_lower = msg_text.lower()
    sent_user_id = user_id_websocket  # This would be the actual user ID for the message sender
    # Check for Commands in the message
    check_for_commands(msg_text, sent_user_id)

async def check_for_staged_events():
    await asyncio.sleep(300)  # Allow some time for the websocket to establish and receive messages
# Check for any commands in the message
def check_for_commands(msg_text_tall, user_sender_id):
    """Check for any commands in the message."""
    chat = get_dm_or_create(user_sender_id)['bubble']['id']
    
    msg_text = msg_text_tall.lower()
    
    
    command = msg_text[1:].split()
    command2 = msg_text_tall[1:].split()
    if msg_text.startswith("!roll"):
        if command.__len__() == 2:
            match = re.fullmatch(r'(\d+)d(\d+)', command[1])
            if match:
                num_dice, sides = map(int, match.groups())
                if user_sender_id == user_id and num_dice == 1 and sides == 500:
                    send_message("Rolling... 500 = 500", main_bubble_ID, media)
                    return

                if (num_dice < 1 or sides < 1):
                    send_message("Invalid input. Number of dice and sides must be greater than 0.", chat, media)
                    return
                if (num_dice > 500 or sides > 1000000):
                    send_message("Invalid input. Number of dice must be less than 500 and sides must be less than 1000000.", chat, media)
                    return
                rolls = [random.randint(1, sides) for _ in range(num_dice)]
                total = sum(rolls)
                rolls_str = " + ".join(map(str, rolls))
                message = f"Rolling... {rolls_str} = {total}"
                if message.__len__() > 500:
                    send_message(message, chat, media)
                else:
                    send_message(message, main_bubble_ID, media)
                return
            else: 
                send_message("Invalid format. Use !roll NdM (e.g., !roll 2d6)", chat, media)
                return
        else:
            send_message("Invalid format. Use !roll NdM (e.g., !roll 2d6)", chat, media)
    if msg_text.startswith("!flip"):
        
        flip = random.choice(["Heads", "Tails"])
        send_message(f"I got... {flip}!", main_bubble_ID, media)
        return
    global triviamaster
    if msg_text.startswith("!trivia"):
        global doing_trivia
        if doing_trivia == 0:
            doing_trivia = 1
            triviamaster = user_sender_id
            print(triviamaster)
            randomint = random.randint(0, all_list.__len__() - 2)
            question = all_list[randomint]
            global quest
            quest = json.loads(question[:-1])
            capquest = quest['question'].capitalize()
            send_message(f"Question: {capquest}", main_bubble_ID, media)
            print(capquest)
            
        else:
            send_message("You cant start anouther trivia right now, one is already running.", chat, media)
    if msg_text.startswith("!reveal"):
        if doing_trivia == 1:
            if user_sender_id in bubble_owners or user_sender_id == triviamaster:
                doing_trivia = 0
                answers = ""
                for i in range(quest['answers'].__len__()):
                    answers += quest['answers'][i].capitalize()
                    print(quest['answers'].__len__())
                    print(i)
                    if i+1 != quest['answers'].__len__():
                        answers += ", "
                send_message(f"Answer(s): {answers}", main_bubble_ID, media)
            else:
                send_message("You dont have permission to reveal the trivia.", chat, media)
        else:
            send_message("There is no trivia right now.", chat, media)
    if msg_text.startswith("!numbergame"):
        if command.__len__() == 2:
            global doing_guess_the_number
            if doing_guess_the_number == 0:

                global max_number
                global correctnumber
                try:
                    max_number = int(command[1])
                except:
                    send_message("Invalid format. Use !numbergame M (e.g., !numbergame 212)", chat, media)
                    return
                if max_number < 1 or max_number > 10000:
                    send_message("Invalid max. Your maximum number must not be less then 1 or greater then 10000", chat, media)
                    return
                doing_guess_the_number = 1
                correctnumber = random.randint(0, max_number+1)
                send_message("Ok! I have chosen my number. User !guess N to guess.", main_bubble_ID, [])
            else:
                send_message("You can't start another guess the number game right now, one is already running.", chat, media)
        else:
            send_message("Invalid format. Use !numbergame M (e.g., !numbergame 212)", chat, media)
    if msg_text.startswith("!guess"):
        if command.__len__() == 2:
            if doing_guess_the_number == 1:
                try:
                    guess = int(command[1])
                except:
                    send_message("Invalid format. Use !guess N (e.g., !guess 212)", chat, media)
                    return
                if (guess < 1 or guess > max_number):
                    send_message("Invalid guess. Your guess must be more then 0 and less then the max number", chat, media)
                    return
                if guess == correctnumber:
                    send_message(f"Correct! The answer was {guess}!", main_bubble_ID, media)
                    doing_guess_the_number = 0
                    return
                elif guess > correctnumber:
                    send_message(f"{guess} is too high!", main_bubble_ID, media)
                elif guess < correctnumber:
                    send_message(f"{guess} is too low!", main_bubble_ID, media)
            else:
                send_message("There is no guess the number game right now.", chat, media)
        else:
            send_message("Invalid format. Use !guess N (e.g., !guess 212)", chat, media)

        
    """if user_sender_id not in bubble_owners:
        send_message("Warning: You do not have permission to use this command.", chat, media)
        return
    else:
        
        elif msg_text.startswith("!poll"):
            if (len(command) == 4):
                
                if command[1] == "time":
                    return
                elif command[1] == "number":
                    return
                return
    send_message(f"Unknown command: '{msg_text}'", main_bubble_ID, media)"""

def get_dm_or_create(sent_user_id):
    matches = list(filter(lambda row: row[0] == sent_user_id, stored_dms))
    if matches.__len__() == 0:
        test = createDM(accesstoken, sent_user_id, 2245)
        data = [
            sent_user_id, test
        ]
        stored_dms.append(data)
        matches = list(filter(lambda row: row[0] == sent_user_id, stored_dms))
    index = stored_dms.index(matches[0])
    return stored_dms[index][1]
    
# Send a message to the API
def send_message(message, bubble, send_media):
    unique_uuid = str(uuid.uuid4())
    messageCreatedat = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    data = {
        "id": "Null",
        "uuid": unique_uuid,
        "bubble_id": bubble,
        "message": message,
        "created_at": messageCreatedat,
        "user_id": user_id,
        "messagemedia": send_media
    }
    url = f"{api_base_url}api/v1/message.create"
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
def upload_file_and_get_key(file_path, filename):
    url = "https://api.pronto.io/api/files"
    try:
        # Open the file and prepare headers
        with open(file_path, 'rb') as file:
            file_content = file.read()
            
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {accesstoken}",
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
            return f"Request failed with status code: {response.status_code}, Error: {response.text}"
    except Exception as e:
        return f"An error occurred: {e}"
"""
#startup stuff
print("This bot was created by:\nTaylan Derstadt (co29) (Lead Dev)\nVajra Vanukuri (co29) (Secondary Dev)\nJimbo Miller (co28) (Secondary Dev)\nAdditional thanks to Greyson Wyler (co29, websocket help) and Paul Estrada (co27, pronto api help)")
while True:
    main_bubble_ID = input("Ender bubble id: ")
    if is_seven_digit_number(main_bubble_ID):
        if check_if_valid_bubble(main_bubble_ID):
            break
        else:
            print("This is not a valid bubble id")
    else:
        print("This is not a valid 7 digit bubble id")

while True:
    log_channel_ID = input("Enter log channel id: ")
    if is_seven_digit_number(log_channel_ID):
        if check_if_valid_bubble(log_channel_ID):
            break
        else:
            print("This is not a valid bubble id")
    else:
        print("This is not a valid 7 digit bubble id")
"""
bubble_id = main_bubble_ID
bubble_info = get_bubble_info(accesstoken, bubble_id)
bubble_owners = [row["user_id"] for row in bubble_info["bubble"]["memberships"] if row["role"] == "owner"]

async def handle_status(request):
    return web.Response(text="Bot is running!", status=200)
async def main_loop():
    # Create an aiohttp web application
    app = web.Application()
    app.router.add_get("/", handle_status)  # Add a route to check status

    # Get the PORT from environment variables or default to 8080
    port = int(os.getenv("PORT", "8080"))

    # Start the aiohttp server
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    print(f"HTTP server running on port {port}")
    await site.start()

    asyncio.create_task(listen_for_commands())
    # Run the WebSocket logic
    await main(main_bubble_ID, bubble_sid)
if user_id in bubble_owners:
    is_bot_owner = True
bubbles = getUsersBubbles(accesstoken)
dms = get_dms(bubbleOverviewJSONPath)
"""[{'id': 3858071, 'title': 'Inara Miyasaka'}, {'id': 3822074, 'title': 'Nathan Muruganantham'}, {'id': 3809608, 'title': 'Sofya Korzh'}, {'id': 3300546, 'title': 'Vajra Vanukuri'}, {'id': 3333256, 'title': 'Weston Yoo'}]"""
global stored_dms
stored_dms = []
bubble_sid = bubble_info["bubble"]["channelcode"]
print(bubble_sid)
if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        print("Server stopped.")
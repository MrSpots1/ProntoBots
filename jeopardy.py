from annotated_types import DocInfo
from networkx import trivial_graph
import websockets
import asyncio
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
import threading

bubbleOverviewJSONPath = createappfolders()
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
user_id = "5301889"
int_user_id = 5301889
main_bubble_ID = "3832006"
log_channel_ID = "4283367"
global media
media = []
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {accesstoken}",
}
game_state = {
    'running': False,
    'round': 1,
    'scores': {},
    'final_registered': [],
    'final_answers': {},
    'answered_users': set(),
    'daily_doubles': set(),
    'buzzed_in': None,
    'buzzed_in_time': 0,
    'current_question': None,
    'current_chooser': None,
    'categories': [],
    'board': [],
    'buzzed': [],
    'buzz_open': False
}
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
with open('jeopardy_questions.json', 'r') as file:
    jeopardy_questions = json.load(file)
global jeopardy_catagories
with open('jeopardy_catagories.json', 'r') as file:
    jeopardy_catagories = json.load(file)
# Minimum number of seconds between messages from the same user before a warning is issued for rate limiting
global ratelimitseconds
ratelimitseconds = 5

global events
events = []
global message_max_length
message_max_length = 750
global triviamaster
triviamaster = 0
# stanfordohs orginization id
global orgID
orgID = 2245

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



# Download Bad Words List
def download_wordlist(url):
    response = requests.get(url)
    if response.status_code == 200:
        words = response.text.split("\n")
        return set(word.strip().lower() for word in words if word.strip())
    else:
        print("Failed to download word list.")
        return set()





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

        # add a check for owners changing to update the bubble_owners and is_bot_owner

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
    await connect_and_listen(bubble_id, bubble_sid)



# Mod Bot Logic for Processing Messages
def process_message(msg_text, user_firstname, user_lastname, timestamp, msg_media, user_id_websocket):
    matches = list(filter(lambda row: row[0] == user_id_websocket, warning_count))
    if matches.__len__() == 0:
        warning_count.append([user_id_websocket, 0])
        matches = list(filter(lambda row: row[0] == user_id_websocket, warning_count))
    msg_text_lower = msg_text.lower()
    sent_user_id = user_id_websocket  # This would be the actual user ID for the message sender
    # Check for Commands in the message
    check_for_commands(msg_text, sent_user_id)


# Check for any commands in the message
def check_for_commands(msg_text_tall, user_sender_id):
    """Check for any commands in the message."""
    chat = get_dm_or_create(user_sender_id)['bubble']['id']

    msg_text = msg_text_tall.lower()

    command = msg_text[1:].split()
    command2 = msg_text_tall[1:].split()
    if msg_text.startswith("!startjeopardy"):
        if not game_state['running']:
            game_state['running'] = True
            game_state['round'] = 1
            game_state['scores'] = {}
            game_state['final_registered'] = []
            game_state['final_answers'] = {}
            game_state['answered_users'] = set()
            game_state['daily_doubles'] = set()
            game_state['buzzed_in'] = None
            game_state['buzzed_in_time'] = 0
            game_state['current_question'] = None
            game_state['current_chooser'] = None
            setup_game_board()
            send_message("🎉 Jeopardy has started! Use !choose [Amount] [Category] to begin!", main_bubble_ID, [])
            display_board()
        else:
            send_message("A game is already running!", chat, [])
    if msg_text.startswith("!choose"):
        if not game_state['running']:
            send_message("No game is currently running.", chat, [])
            return

        if len(command) < 3:
            send_message("Usage: !choose [Amount] [Category]", chat, [])
            return

        try:
            points = int(command[1])
        except:
            send_message("Invalid point value.", chat, [])
            return

        category = " ".join(command2[2:])
        if category not in game_state['categories']:
            send_message("Invalid category!", chat, [])
            return

        for q in game_state['board']:
            if q['category_id'] == category and int(q['points']) == points:
                if random.random() < 0.1 and (category, points) not in game_state['daily_double_used']:
                    game_state['daily_double_used'].add((category, points))
                    send_message("Daily Double! Use !dailydouble [amount] [answer]", main_bubble_ID, [])
                    game_state['current_question'] = q
                    return
                post_question(q)
                return

        send_message("Couldn't find a valid question at that amount in that category.", chat, [])

    if msg_text.startswith("!buzz"):
        if game_state['buzzed_in'] is None and game_state['current_question']:
            game_state['buzzed_in'] = user_sender_id
            game_state['buzzed_in_time'] = time.time()
            send_message(f"<@{user_sender_id}> has buzzed in! You have 20 seconds to answer with !answer [your answer]", main_bubble_ID, [])
        else:
            send_message("Someone has already buzzed in or there's no active question.", chat, [])

    if msg_text.startswith("!answer"):
        if user_sender_id != game_state['buzzed_in']:
            send_message("You didn't buzz in!", chat, [])
            return

        if time.time() - game_state['buzzed_in_time'] > 20:
            send_message("Time's up!", main_bubble_ID, [])
            game_state['buzzed_in'] = None
            display_board()
            return

        answer_text = " ".join(command2[1:]).lower()
        correct_answers = [ans.lower() for ans in game_state['current_question']['answers']]

        uid = str(user_sender_id)
        points = int(game_state['current_question']['points'])
        game_state['scores'].setdefault(uid, 0)

        if answer_text in correct_answers:
            game_state['scores'][uid] += points
            send_message(f"Correct! <@{user_sender_id}> gains {points} points.", main_bubble_ID, [])
            game_state['current_chooser'] = user_sender_id
            game_state['current_question'] = None
        else:
            game_state['scores'][uid] -= points
            send_message(f"Incorrect! <@{user_sender_id}> loses {points} points.", main_bubble_ID, [])
            game_state['buzzed_in'] = None
        display_board()

    if msg_text.startswith("!dailydouble"):
        if game_state['current_question'] is None:
            send_message("There's no active daily double right now.", chat, [])
            return

        parts = command2[1:]
        if len(parts) < 2:
            send_message("Usage: !dailydouble [amount] [answer]", chat, [])
            return

        try:
            wager = int(parts[0])
        except:
            send_message("Invalid wager.", chat, [])
            return

        uid = str(user_sender_id)
        score = game_state['scores'].get(uid, 0)
        wager = max(1, min(wager, max(score, 1000 if game_state['round'] == 1 else 2000)))

        answer_text = " ".join(parts[1:]).lower()
        correct_answers = [ans.lower() for ans in game_state['current_question']['answers']]

        game_state['scores'].setdefault(uid, 0)
        if answer_text in correct_answers:
            game_state['scores'][uid] += wager
            send_message(f"Correct! <@{user_sender_id}> gains {wager} points.", main_bubble_ID, [])
        else:
            game_state['scores'][uid] -= wager
            send_message(f"Incorrect! <@{user_sender_id}> loses {wager} points.", main_bubble_ID, [])

        game_state['current_question'] = None
        display_board()

    if msg_text.startswith("!score"):
        scores = sorted(game_state['scores'].items(), key=lambda x: x[1], reverse=True)
        output = "🏆 Current Scores:\n" + "\n".join(f"<@{uid}>: {score}" for uid, score in scores)
        send_message(output, main_bubble_ID, [])

    if msg_text.startswith("!register"):
        uid = str(user_sender_id)
        score = game_state['scores'].get(uid, 0)
        if score < 1:
            send_message("You need at least $1 to register for Final Jeopardy.", chat, [])
        elif uid not in game_state['final_registered']:
            game_state['final_registered'].append(uid)
            send_message(f"You've registered for Final Jeopardy! Your current score is ${score}.", chat, [])
        else:
            send_message("You're already registered!", chat, [])

def setup_game_board():
    chosen_categories = random.sample(jeopardy_catagories, 6)
    game_state['categories'] = chosen_categories
    game_state['board'] = []

    for cat in chosen_categories:
        questions = [q for q in jeopardy_questions if q['category_id'] == cat]
        unique_points = sorted(set(int(q['points']) for q in questions))
        selected = [random.choice([q for q in questions if int(q['points']) == pts]) for pts in unique_points if [q for q in questions if int(q['points']) == pts]]
        game_state['board'].extend(selected)
    print("🔧 Jeopardy board is set up!", main_bubble_ID, [])


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

def start_final_jeopardy():
    send_message("Final Jeopardy is starting in 1 minute! Use !register to join.", main_bubble_ID, [])
    time.sleep(60)

    if not game_state['final_registered']:
        send_message("No one registered for Final Jeopardy!", main_bubble_ID, [])
        return

    # Choose a final jeopardy question
    final_q = random.choice(jeopardy_questions)
    game_state['current_question'] = final_q

    for uid in game_state['final_registered']:
        dm = get_dm_or_create(int(uid))['bubble']['id']
        score = game_state['scores'].get(uid, 0)
        send_message(f"Final Jeopardy Question:\n{final_q['question']}\n\nWager and answer using:\n!finaljeopardy [amount] [your answer]", dm, [])

    time.sleep(120)  # 2 minutes for answers

    for uid in game_state['final_registered']:
        bubble = get_dm_or_create(int(uid))['bubble']['id']
        msg = get_last_message(bubble)
        if not msg.startswith("!finaljeopardy"):
            continue

        parts = msg.split()
        if len(parts) < 3:
            continue

        try:
            wager = int(parts[1])
        except:
            continue

        if wager <= 0:
            continue

        answer_text = " ".join(parts[2:]).lower()
        correct_answers = [ans.lower() for ans in final_q['answers']]
        user_score = game_state['scores'].get(uid, 0)

        if wager > user_score:
            wager = user_score

        if answer_text in correct_answers:
            game_state['scores'][uid] += wager
            send_message(f"{uid} got it RIGHT and gained ${wager}!", main_bubble_ID, [])
        else:
            game_state['scores'][uid] -= wager
            send_message(f"{uid} got it WRONG and lost ${wager}.", main_bubble_ID, [])

    scores = sorted(game_state['scores'].items(), key=lambda x: x[1], reverse=True)
    leaderboard = "🏁 Final Scores:\n"
    for uid, score in scores:
        leaderboard += f"{uid}: ${score}\n"
    send_message(leaderboard, main_bubble_ID, [])
    game_state['running'] = False


def display_board():
    board = {cat: [] for cat in game_state['categories']}
    for q in jeopardy_questions:
        cat = q['category_id']
        pts = int(q['points'])
        used = q not in game_state['board']
        if cat in board:
            board[cat].append((pts, used))
    msg = "Jeopardy Board:\n"
    for cat in board:
        msg += f"\n{cat}:\n"
        for pts, used in sorted(board[cat], key=lambda x: x[0]):
            msg += f" {'❌' if used else f'${pts}'} "
        msg += "\n"
    send_message(msg, main_bubble_ID, [])

# Send a message to the API

# ========== Post a Question with Timeout ==========
def post_question(question_obj):
    game_state['current_question'] = question_obj
    game_state['buzzed'] = []
    game_state['buzz_open'] = True

    question = question_obj['question']
    send_message(f"Question for ${question_obj['points']} in {question_obj['category_id']}:\n{question}", main_bubble_ID, [])

    def buzz_timeout():
        time.sleep(10)
        if not game_state['buzzed_in'] and game_state['buzz_open']:
            game_state['buzz_open'] = False
            reveal_answer_timeout(question_obj)

    threading.Thread(target=buzz_timeout).start()


def reveal_answer_timeout(question_obj):
    corrects = ", ".join(question_obj['answers'])
    send_message(f"⏱ Time’s up! No one buzzed in. The correct answer was: {corrects}", main_bubble_ID, [])

    if question_obj in game_state['board']:
        game_state['board'].remove(question_obj)

    game_state['current_question'] = None
    display_board()



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

def get_last_message(bubbleID):
    url = f"{API_BASE_URL}api/v1/bubble.history"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {accesstoken}",
    }
    request_payload = {"bubble_id": bubbleID}
    latestMessageID = None
    if latestMessageID is not None:
        request_payload["latest"] = latestMessageID

    try:
        response = requests.post(url, headers=headers, json=request_payload)
        response.raise_for_status()
        response_json = response.json()

        return response_json['messages'][0]['message']
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error occurred: {http_err} - Response: {response.text}")
        if response.status_code == 401:
            raise BackendError(f"HTTP error occurred: {http_err}")
        else:
            raise BackendError(f"HTTP error occurred: {http_err}")
    except requests.exceptions.RequestException as req_err:
        logger.error(f"Request exception occurred: {req_err}")
        raise BackendError(f"Request exception occurred: {req_err}")
    except Exception as err:
        logger.error(f"An unexpected error occurred: {err}")
        raise BackendError(f"An unexpected error occurred: {err}")




bubble_id = main_bubble_ID
bubble_info = get_bubble_info(accesstoken, bubble_id)
bubble_owners = [row["user_id"] for row in bubble_info["bubble"]["memberships"] if row["role"] == "owner"]

if user_id in bubble_owners:
    is_bot_owner = True

stored_dms = []
bubble_sid = bubble_info["bubble"]["channelcode"]
print(bubble_sid)
asyncio.run(main(bubble_id, bubble_sid))
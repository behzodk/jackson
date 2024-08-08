from flask import Flask, request, g, render_template, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
import sqlite3
import logging
import os
import random
import requests
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('TOKEN')

app = Flask(__name__)
socketio = SocketIO(app)
DATABASE = 'logs.db'

TELEGRAM_API_URL = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
UPLOAD_FOLDER = 'static/photos'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    return db

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message TEXT NOT NULL,
                is_command INTEGER NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_photos (
                user_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                photo_count INTEGER NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                photo_path TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES user_photos(user_id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS secret_word (
                id INTEGER PRIMARY KEY,
                word TEXT NOT NULL
            )
        ''')
        cursor.execute("INSERT INTO secret_word (id, word) VALUES (1, 'uh-808') ON CONFLICT(id) DO NOTHING")
        db.commit()

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def generate_unique_username(first_name):
    unique_id = random.randint(1000, 9999)
    return f"{first_name}_{unique_id}"

@app.route('/', methods=['GET'])
def index():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT message, is_command FROM logs")
    logs = cursor.fetchall()
    if not logs:
        logs = [("No logs yet. Interact with the bot to generate logs.", 0)]
    return render_template('index.html', logs=logs)

@app.route('/images', methods=['GET'])
def images():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT photo_path FROM photos")
    photos = cursor.fetchall()
    return render_template('images.html', photos=photos)

@app.route('/fetch_logs', methods=['GET'])
def fetch_logs():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT message, is_command FROM logs")
    logs = cursor.fetchall()
    return jsonify(logs)

@app.route('/logs', methods=['POST'])
def log_message():
    try:
        message = request.form['message']
        db = get_db()
        cursor = db.cursor()
        cursor.execute("INSERT INTO logs (message, is_command) VALUES (?, ?)", (message, 0))
        db.commit()
        app.logger.info(message)
        socketio.emit('new_log', {'message': message, 'is_command': 0})
        return 'Logged', 200
    except Exception as e:
        app.logger.error(f"Error logging message: {e}")
        return 'Error', 500

@app.route('/register_user', methods=['POST'])
def register_user():
    try:
        user_id = request.form['user_id']
        username = request.form['username']
        first_name = request.form['first_name']

        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT * FROM user_photos WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        if not result:
            cursor.execute("INSERT INTO user_photos (user_id, username, photo_count) VALUES (?, ?, ?)", (user_id, username, 0))
            db.commit()
        return 'Registered', 200
    except Exception as e:
        app.logger.error(f"Error registering user: {e}")
        return 'Error', 500

@app.route('/update_photo_count', methods=['POST'])
def update_photo_count():
    try:
        user_id = request.form['user_id']
        username = request.form['username']
        first_name = request.form['first_name']
        reset = request.form.get('reset', 'false') == 'true'

        if not username:
            username = generate_unique_username(first_name)

        db = get_db()
        cursor = db.cursor()
        if reset:
            cursor.execute("UPDATE user_photos SET photo_count = 0 WHERE user_id = ?", (user_id,))
        else:
            cursor.execute("SELECT photo_count FROM user_photos WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            if result:
                new_count = result[0] + 1
                cursor.execute("UPDATE user_photos SET photo_count = ? WHERE user_id = ?", (new_count, user_id))
            else:
                new_count = 1
                cursor.execute("INSERT INTO user_photos (user_id, username, photo_count) VALUES (?, ?, ?)", (user_id, username, new_count))
        db.commit()
        return jsonify({'photo_count': new_count})
    except Exception as e:
        app.logger.error(f"Error updating photo count: {e}")
        return jsonify({'photo_count': 0}), 500

@app.route('/get_photo_count', methods=['GET'])
def get_photo_count():
    try:
        user_id = request.args.get('user_id')
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT photo_count FROM user_photos WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        if result:
            return jsonify({'photo_count': result[0]})
        return jsonify({'photo_count': 0})
    except Exception as e:
        app.logger.error(f"Error getting photo count: {e}")
        return jsonify({'photo_count': 0}), 500

@app.route('/get_secret_word', methods=['GET'])
def get_secret_word():
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT word FROM secret_word WHERE id = 1")
        result = cursor.fetchone()
        if result:
            return jsonify({'secret_word': result[0]})
        return jsonify({'secret_word': 'uh-808'})  # Fallback in case of an issue
    except Exception as e:
        app.logger.error(f"Error getting secret word: {e}")
        return jsonify({'secret_word': 'uh-808'}), 500

@app.route('/check_secret', methods=['GET'])
def check_secret():
    try:
        user_id = request.args.get('user_id')
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT photo_count FROM user_photos WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        if result and result[0] >= 4:
            return jsonify({'eligible': True})
        return jsonify({'eligible': False})
    except Exception as e:
        app.logger.error(f"Error checking secret: {e}")
        return jsonify({'eligible': False}), 500

@app.route('/upload_photo', methods=['POST'])
def upload_photo():
    try:
        user_id = request.form['user_id']
        photo = request.files['photo']
        filename = f'{photo.filename}'
        photo_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        photo.save(photo_path)
        
        photo_path = photo_path.replace('static/', '')  # Adjust the path for rendering
        db = get_db()
        cursor = db.cursor()
        cursor.execute("INSERT INTO photos (user_id, photo_path) VALUES (?, ?)", (user_id, photo_path))
        db.commit()
        return 'Photo uploaded', 200
    except Exception as e:
        app.logger.error(f"Error uploading photo: {e}")
        return 'Error', 500

@app.route('/execute_command', methods=['POST'])
def execute_command():
    command = request.form['command']
    parts = command.split()
    db = get_db()
    cursor = db.cursor()

    try:
        if len(parts) == 3 and parts[0] == '/count' and parts[1] == 'photo':
            username = parts[2]
            cursor.execute("SELECT photo_count FROM user_photos WHERE username = ?", (username,))
            result = cursor.fetchone()
            if result:
                result_message = f"Count of photos by {username}: {result[0]}"
            else:
                result_message = "Error in command, or there is no user with that username."
        elif len(parts) == 2 and parts[0] == '/count' and parts[1] == 'users':
            cursor.execute("SELECT COUNT(*) FROM user_photos")
            result = cursor.fetchone()
            result_message = f"Count of users: {result[0]}"
        elif len(parts) == 2 and parts[0] == '/show' and parts[1] == 'users':
            cursor.execute("SELECT username FROM user_photos")
            result = cursor.fetchall()
            if result:
                user_list = "<br>".join([f"{i+1}. {username[0]}" for i, username in enumerate(result)])
                result_message = f"Users:<br>{user_list}"
            else:
                result_message = "No users found."
        elif len(parts) == 2 and parts[0] == '/show' and parts[1] == 'secret':
            cursor.execute("SELECT word FROM secret_word WHERE id = 1")
            result = cursor.fetchone()
            if result:
                result_message = f"Current secret word: {result[0]}"
            else:
                result_message = "Secret word not found."
        elif len(parts) == 3 and parts[0] == '/change' and parts[1] == 'secret':
            new_secret = parts[2]
            cursor.execute("UPDATE secret_word SET word = ? WHERE id = 1", (new_secret,))
            db.commit()
            result_message = f"Secret word changed to: {new_secret}"
        elif parts[0] == '/sendmessage':
            try:
                who = command.split('who=')[1].split(' ')[0]
                message_start = command.index('message="') + len('message="')
                message_end = command.rindex('"')
                message_text = command[message_start:message_end]

                if who == 'all':
                    cursor.execute("SELECT user_id, username FROM user_photos")
                    results = cursor.fetchall()
                    if results:
                        for user_id, username in results:
                            send_telegram_message(user_id, message_text)
                        result_message = f"Message sent to all users: {message_text}"
                    else:
                        result_message = "Error: No users found."
                else:
                    cursor.execute("SELECT user_id FROM user_photos WHERE username = ?", (who,))
                    result = cursor.fetchone()
                    if result:
                        user_id = result[0]
                        send_telegram_message(user_id, message_text)
                        result_message = f"Message sent to {who}: {message_text}"
                    else:
                        result_message = f"Error: User with username {who} not found."
            except Exception as e:
                result_message = f"Error parsing sendmessage command: {e}"
        elif len(parts) == 1 and parts[0] == '/help':
            result_message = "Available commands:<br>" \
                             "/count photo {username} - Get the number of photos by the user<br>" \
                             "/count users - Get the total number of users<br>" \
                             "/show users - Show the list of users<br>" \
                             "/show secret - Show the current secret word<br>" \
                             "/change secret {new_secret} - Change the secret word<br>" \
                             "/sendmessage who={username} message=\"{message}\" - Send a message to a user<br>" \
                             "/sendmessage who=all message=\"{message}\" - Send a message to all users<br>" \
                             "/getphotos by=all - Show all photos<br>" \
                             "/getphotos by={username} - Show photos by a specific user"
        elif len(parts) == 2 and parts[0] == '/getphotos' and parts[1].startswith('by='):
            by_value = parts[1][3:]
            if by_value == 'all':
                cursor.execute("SELECT photo_path FROM photos")
                photos = cursor.fetchall()
                if photos:
                    photos_list = "<br>".join([f"<img src='/static/{photo[0]}' style='max-width: 100%; height: auto;'>" for photo in photos])
                    result_message = f"Photos:<br>{photos_list}"
                else:
                    result_message = "No photos found."
            else:
                cursor.execute("SELECT user_id FROM user_photos WHERE username = ?", (by_value,))
                user = cursor.fetchone()
                if user:
                    cursor.execute("SELECT photo_path FROM photos WHERE user_id = ?", (user[0],))
                    photos = cursor.fetchall()
                    if photos:
                        photos_list = "<br>".join([f"<img src='/static/{photo[0]}' style='max-width: 100%; height: auto;'>" for photo in photos])
                        result_message = f"Photos by {by_value}:<br>{photos_list}"
                    else:
                        result_message = f"No photos found for user {by_value}."
                else:
                    result_message = f"Error: No user with username {by_value} found."
        else:
            result_message = "Error in command, or there is no such kind of command."

        # Log the command
        cursor.execute("INSERT INTO logs (message, is_command) VALUES (?, ?)", (command, 1))
        db.commit()

        # Log the result message
        cursor.execute("INSERT INTO logs (message, is_command) VALUES (?, ?)", (result_message, 0))
        db.commit()

        # Emit the result message to WebSocket clients
        socketio.emit('new_log', {'message': result_message, 'is_command': 0})

        # Fetch logs again for the updated log
        cursor.execute("SELECT message, is_command FROM logs")
        logs = cursor.fetchall()

        return render_template('index.html', logs=logs, photos=[])
    except Exception as e:
        app.logger.error(f"Error executing command: {e}")
        return "Internal Server Error", 500

def send_telegram_message(user_id, message_text):
    payload = {
        'chat_id': user_id,
        'text': message_text
    }
    try:
        response = requests.post(TELEGRAM_API_URL, data=payload)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error sending message: {e}")

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    init_db()
    socketio.run(app, port=5000)
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import requests
import os
import random
from telegram.error import TimedOut
import os
from dotenv import load_dotenv

load_dotenv()

token = os.getenv('TOKEN')

try:
    FLASK_SERVER_URL = 'http://127.0.0.1:5000/logs'
    UPDATE_PHOTO_COUNT_URL = 'http://127.0.0.1:5000/update_photo_count'
    REGISTER_USER_URL = 'http://127.0.0.1:5000/register_user'
    GET_PHOTO_COUNT_URL = 'http://127.0.0.1:5000/get_photo_count'
    CHECK_SECRET_URL = 'http://127.0.0.1:5000/check_secret'
    GET_SECRET_WORD_URL = 'http://127.0.0.1:5000/get_secret_word'
    UPLOAD_PHOTO_URL = 'http://127.0.0.1:5000/upload_photo'
    TOKEN = token

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        username = user.username
        first_name = user.first_name
        user_id = user.id

        if not username:
            username = generate_unique_username(first_name)

        await update.message.reply_text("Hello. Send me four photos (with compression), and I will send you a secret word.")

        log_message(f"{username} started chat")

        # Register user in the Flask app
        data = {
            'user_id': user_id,
            'username': username,
            'first_name': first_name
        }
        requests.post(REGISTER_USER_URL, data=data)

    async def handle_photos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        user_id = user.id
        username = user.username
        first_name = user.first_name

        if not username:
            username = generate_unique_username(first_name)

        # Download the photo
        photo_file = await context.bot.getFile(update.message.photo[-1].file_id)
        photo_path = os.path.join('static/photos/', f'{photo_file.file_id}.jpg')
        await photo_file.download_to_drive(photo_path)

        # Upload the photo to the Flask server
        with open(photo_path, 'rb') as photo:
            files = {'photo': photo}
            data = {'user_id': user_id}
            response = requests.post(UPLOAD_PHOTO_URL, files=files, data=data)
            response.raise_for_status()

        try:
            # Get the current photo count from the Flask app
            response = requests.get(GET_PHOTO_COUNT_URL, params={'user_id': user_id})
            response.raise_for_status()  # Raise an error for bad status codes
            photo_count = response.json().get('photo_count', 0)
        except requests.exceptions.RequestException as e:
            print(f"Error getting photo count: {e}")
            photo_count = 0

        photo_count += 1
        log_message(f"{username} sent photo")

        if photo_count >= 4:
            try:
                # Get the current secret word from the Flask app
                response = requests.get(GET_SECRET_WORD_URL)
                response.raise_for_status()
                secret_word = response.json().get('secret_word', 'uh-808')
            except requests.exceptions.RequestException as e:
                print(f"Error getting secret word: {e}")
                secret_word = 'uh-808'

            await update.message.reply_text(f"secret: {secret_word}")
            data = {
                'user_id': user_id,
                'username': username,
                'first_name': first_name,
                'reset': True
            }
            requests.post(UPDATE_PHOTO_COUNT_URL, data=data)
        else:
            await update.message.reply_text(f"{photo_count} photo(s) received. Please send more photos.")
            # Update the photo count in the Flask app
            data = {
                'user_id': user_id,
                'username': username,
                'first_name': first_name
            }
            requests.post(UPDATE_PHOTO_COUNT_URL, data=data)

    async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        username = user.username
        first_name = user.first_name
        message_text = update.message.text

        if not username:
            username = generate_unique_username(first_name)

        log_message(f"{username} said: {message_text}")

        # Respond with the specific message
        await update.message.reply_text("Please, do not disturb me, I am fucking lazy, mind your own business. You wanna send pictures, feel free, otherwise, pnx")

    async def secret(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        user_id = user.id
        username = user.username
        first_name = user.first_name

        if not username:
            username = generate_unique_username(first_name)

        try:
            response = requests.get(CHECK_SECRET_URL, params={'user_id': user_id})
            response.raise_for_status()  # Raise an error for bad status codes
            eligible = response.json().get('eligible', False)
        except requests.exceptions.RequestException as e:
            print(f"Error checking secret eligibility: {e}")
            eligible = False

        if eligible:
            try:
                # Get the current secret word from the Flask app
                response = requests.get(GET_SECRET_WORD_URL)
                response.raise_for_status()
                secret_word = response.json().get('secret_word', 'uh-808')
            except requests.exceptions.RequestException as e:
                print(f"Error getting secret word: {e}")
                secret_word = 'uh-808'

            await update.message.reply_text(f"secret: {secret_word}")
        else:
            await update.message.reply_text("You are not eligible for the secret word yet. Please send four photos.")

    def log_message(message):
        try:
            requests.post(FLASK_SERVER_URL, data={'message': message})
        except requests.exceptions.RequestException as e:
            print(f"Error logging message: {e}")

    def generate_unique_username(first_name):
        unique_id = random.randint(1000, 9999)
        return f"{first_name}_{unique_id}"

    # Create the Application
    app = ApplicationBuilder().token(TOKEN).build()

    # Add the command handler to the application
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("secret", secret))

    # Add the photo handler to the application
    app.add_handler(MessageHandler(filters.PHOTO, handle_photos))

    # Add the text message handler to the application
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Run the bot
    app.run_polling()
except TimedOut:
    print("Down time")
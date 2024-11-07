import eventlet
eventlet.monkey_patch()

from flask import Flask, jsonify, request
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from contextlib import contextmanager
from typing import Optional, Tuple
import logging
import os
import pymssql

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")  # Use eventlet async mode

# Configuration for Azure SQL Server
class Config:
    SQL_SERVER = 'gatheringfunctionserver.database.windows.net'
    SQL_DATABASE = 'GatheringFunctionDB'
    SQL_USERNAME = 'Sachindu'
    SQL_PASSWORD = os.getenv('SQL_PASSWORD', 'Qwerty@1234')  # Use environment variable or default

# Database connection management
@contextmanager
def get_db_cursor():
    connection = None
    cursor = None
    try:
        connection = pymssql.connect(
            server=Config.SQL_SERVER,
            database=Config.SQL_DATABASE,
            user=Config.SQL_USERNAME,
            password=Config.SQL_PASSWORD
        )
        cursor = connection.cursor()
        logging.info("Database connection established successfully.")
        yield cursor
        connection.commit()
    except pymssql.Error as e:
        if connection:
            connection.rollback()
        logging.error(f"Database error: {e}")
        raise
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
            logging.info("Database connection closed.")

# Retrieve user data from the database
def get_user_data_from_db(user_id: str) -> Optional[Tuple]:
    try:
        with get_db_cursor() as cursor:
            query = "SELECT name, access_level, photos_taken FROM users WHERE user_id = %s"
            cursor.execute(query, (user_id,))
            return cursor.fetchone()
    except pymssql.Error as e:
        logging.error(f"Database error in get_user_data_from_db: {e}")
        return None

# Socket event to handle user scan
@socketio.on('scan_user')
def handle_scan_user(user_id: str):
    try:
        user_data = get_user_data_from_db(user_id)
        if user_data:
            message = f"Welcome {user_data[0]}"
            logging.info(f"Emitting welcome_message: {message}")
            socketio.emit('welcome_message', message)
        else:
            logging.warning(f"User not found for user_id: {user_id}")
            socketio.emit('welcome_message', "User not found")
    except Exception as e:
        logging.error(f"Error in handle_scan_user: {e}")
        socketio.emit('welcome_message', "Error occurred while scanning user")

# API endpoint to get user data
@app.route('/get_user_data', methods=['GET'])
def get_user_data():
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({'error': 'User ID is required'}), 400

        user_data = get_user_data_from_db(user_id)
        
        if user_data:
            response = {
                'name': user_data[0],
                'access_level': user_data[1],
                'photos_taken': user_data[2]
            }
            logging.info(f"User data retrieved successfully for user_id: {user_id}")
            return jsonify(response), 200
        logging.warning(f"User not found for user_id: {user_id}")
        return jsonify({'error': 'User not found'}), 404

    except pymssql.Error as e:
        logging.error(f"Database error in get_user_data: {e}")
        return jsonify({'error': 'Database error occurred'}), 500
    except Exception as e:
        logging.error(f"Unexpected error in get_user_data: {e}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

# API endpoint to update photos taken
@app.route('/update_photos_taken', methods=['POST'])
def update_photos_taken():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        user_id = data.get('user_id')
        access_level = data.get('access_level')

        if not all([user_id, access_level]):
            return jsonify({'error': 'Missing required fields'}), 400

        with get_db_cursor() as cursor:
            # Get current photos taken
            query = "SELECT photos_taken, access_level FROM users WHERE user_id = %s"
            cursor.execute(query, (user_id,))
            user_data = cursor.fetchone()

            if not user_data:
                return jsonify({'error': 'User not found'}), 404

            current_photos, stored_access_level = user_data

            # Verify access level matches database
            if stored_access_level != access_level:
                return jsonify({'error': 'Invalid access level'}), 403

            # Check photo limits
            max_photos = 2 if access_level == 'management' else 1
            if current_photos >= max_photos:
                return jsonify({'error': 'Maximum photos taken'}), 400

            # Update photos taken
            update_query = "UPDATE users SET photos_taken = photos_taken + 1 WHERE user_id = %s"
            cursor.execute(update_query, (user_id,))

            logging.info(f"Photos taken updated successfully for user_id: {user_id}")
            return jsonify({'message': 'Photo taken successfully'}), 200

    except pymssql.Error as e:
        logging.error(f"Database error in update_photos_taken: {e}")
        return jsonify({'error': 'Database error occurred'}), 500
    except Exception as e:
        logging.error(f"Unexpected error in update_photos_taken: {e}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

# Endpoint to test scan user function
@app.route('/test_scan_user', methods=['POST'])
def test_scan_user():
    data = request.get_json()
    user_id = data.get('user_id')
    
    if not user_id:
        return jsonify({'error': 'User ID is required'}), 400

    # Manually call the handle_scan_user function
    handle_scan_user(user_id)
    logging.info(f"Scan event triggered successfully for user_id: {user_id}")
    return jsonify({'message': 'Scan event triggered successfully'}), 200

# New endpoint to emit scan_user event
@app.route('/emit_scan_user', methods=['POST'])
def emit_scan_user():
    data = request.get_json()
    user_id = data.get('user_id')
    
    if not user_id:
        return jsonify({'error': 'User ID is required'}), 400

    socketio.emit('scan_user', user_id)
    logging.info(f"scan_user event emitted successfully for user_id: {user_id}")
    return jsonify({'message': 'Scan user event emitted successfully'}), 200

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    # Check database connection
    try:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT 1")
            logging.info("Database connection established successfully.")
    except pymssql.Error as e:
        logging.error(f"Database connection error: {e}")
        logging.info("Failed to connect to the database. Exiting the application.")
        exit(1)

    socketio.run(app, host='0.0.0.0', port=5000)
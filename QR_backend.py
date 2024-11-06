from flask import Flask, jsonify, request
from flask_socketio import SocketIO
import MySQLdb
from contextlib import contextmanager
from typing import Optional, Tuple
import logging
import os

app = Flask(__name__)
socketio = SocketIO(app)

import MySQLdb
import os
import logging
from contextlib import contextmanager

# Configuration for Azure MySQL
class Config:
    MYSQL_HOST = 'gatheringfunctionserver.database.windows.net'
    MYSQL_USER = os.getenv('MYSQL_USER', 'Sachindu')  # User from environment variable or default
    MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', 'Qwerty@1234')  # Password from environment variable or default
    MYSQL_DB = 'GatheringFunctionDB'

# Database connection management
@contextmanager
def get_db_cursor():
    connection = None
    cursor = None
    try:
        connection = MySQLdb.connect(
            host=Config.MYSQL_HOST,
            user=Config.MYSQL_USER,
            passwd=Config.MYSQL_PASSWORD,
            db=Config.MYSQL_DB,
            connect_timeout=10,  # Connection timeout set to 10 seconds
            ssl={'ssl': {}}  # Enable SSL encryption
        )
        cursor = connection.cursor()
        print("Database connection established successfully.")  # Print success message
        yield cursor
        connection.commit()
    except MySQLdb.Error as e:
        if connection:
            connection.rollback()
        logging.error(f"Database error: {e}")
        print("Failed to connect to the database.")  # Print failure message
        raise
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
            print("Database connection closed.")  # Print closure message


# Retrieve user data from the database
def get_user_data_from_db(user_id: str) -> Optional[Tuple]:
    with get_db_cursor() as cursor:
        query = "SELECT name, access_level, photos_taken FROM users WHERE user_id = %s"
        cursor.execute(query, (user_id,))
        return cursor.fetchone()

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
            return jsonify(response), 200
        return jsonify({'error': 'User not found'}), 404

    except MySQLdb.Error as e:
        logging.error(f"Database error in get_user_data: {e}")
        return jsonify({'error': 'Database error occurred'}), 500
    except Exception as e:
        logging.error(f"Unexpected error in get_user_data: {e}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

# Socket event to handle user scan
@socketio.on('scan_user')
def handle_scan_user(user_id: str):
    try:
        with get_db_cursor() as cursor:
            query = "SELECT name FROM users WHERE user_id = %s"
            cursor.execute(query, (user_id,))
            user_data = cursor.fetchone()
            
            message = f"Welcome {user_data[0]}" if user_data else "User not found"
            socketio.emit('welcome_message', message)
    except Exception as e:
        logging.error(f"Error in handle_scan_user: {e}")
        socketio.emit('welcome_message', "Error occurred while scanning user")

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

            return jsonify({'message': 'Photo taken successfully'}), 200

    except MySQLdb.Error as e:
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
    return jsonify({'message': 'Scan event triggered successfully'}), 200

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    # Check database connection
    try:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT 1")
            print("Database connection established successfully.")
    except MySQLdb.Error as e:
        logging.error(f"Database connection error: {e}")
        print("Failed to connect to the database. Exiting the application.")
        exit(1)

    socketio.run(app, host='0.0.0.0', port=5000)

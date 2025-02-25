# Django Chat App Backend

This is the backend for a real-time chat application built with Django, Django REST Framework, and Channels. It provides API endpoints for user authentication, team management, channel management, and message handling using WebSockets.

## Features

-   **User Authentication:**
    -   Registration and login using Django REST Framework and Simple JWT.
    -   Token-based authentication for API endpoints.
-   **Team Management:**
    -   Create, update, and delete teams.
    -   Add and remove members from teams.
    -   Team invitation system with unique invite codes and expiration.
-   **Channel Management:**
    -   Create, update, and delete channels within teams.
    -   Automatic membership synchronization with the team.
-   **Message Handling:**
    -   Send and receive messages in real-time using WebSockets (Channels).
    -   Support for both channel messages and direct messages.
    -   Message replies.
-   **Real-time Communication:**
    -   Utilizes Django Channels for WebSocket-based real-time communication.
    -   Integration with Redis for channel layer.
-   **API Endpoints:**
    -   RESTful API design using Django REST Framework.
    -   Comprehensive set of endpoints for managing users, teams, channels, and messages.
-   **CORS Support:**
    -   Configured to allow cross-origin requests from any origin for development purposes.

## Technologies Used

-   **Django:** Web framework
-   **Django REST Framework:** Toolkit for building REST APIs
-   **Django Channels:** Extends Django to handle WebSockets
-   **Redis:** In-memory data structure store, used as a channel layer for Channels
-   **Simple JWT:** JSON Web Token authentication for Django REST Framework
-   **PostgreSQL:** Database

## Setup Instructions

### Prerequisites

-   Python 3.8+
-   PostgreSQL
-   Redis

### Installation

1.  Clone the repository:

    ```
    git clone <repository_url>
    cd backend
    ```

2.  Create a virtual environment:

    ```
    python -m venv venv
    source venv/bin/activate   # On Linux/macOS
    venv\Scripts\activate      # On Windows
    ```

3.  Install the dependencies:

    ```
    pip install -r requirements.txt
    ```

4.  Configure the database:

    -   Update the `DATABASES` settings in `backend/settings.py` with your PostgreSQL credentials.

    ```
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': 'chatapp',
            'USER': 'testuser',
            'PASSWORD': '12345',
            'HOST': 'localhost',
            'PORT': '5432',
        }
    }
    ```

5.  Configure Redis:

    -   Ensure Redis is running on the default host and port (127.0.0.1:6379).
    -   The `CHANNEL_LAYERS` setting in `backend/settings.py` is pre-configured for this.

    ```
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                "hosts": [('127.0.0.1', 6379)],
            },
        },
    }
    ```

6.  Set the secret key:

    -   In `backend/settings.py`, change the `SECRET_KEY` to a secure, random value, especially for production.
    -   **Do not use the insecure example key in production.**

    ```
    SECRET_KEY = 'your-secret-key'  # Replace with a secure key
    ```

7.  Run migrations:

    ```
    python manage.py migrate
    ```

8.  Create a superuser:

    ```
    python manage.py createsuperuser
    ```

9.  Run the development server:

    ```
    python manage.py runserver
    ```

10. Run the Daphne ASGI server:

    ```
    daphne backend.asgi:application
    ```

## Environment Variables

It is recommended to use environment variables for sensitive information such as the `SECRET_KEY` and database credentials. You can use a library like `python-dotenv` to manage these variables.

## CORS Configuration

The `CORS_ALLOW_ALL_ORIGINS = True` setting is used to allow cross-origin requests from any origin. This is suitable for development but should be configured more strictly in production to only allow requests from your specific frontend domain.

## Project Structure

backend/
├── accounts/ # User account management app
├── chat/ # Chat functionality app (models, serializers, viewsets)
├── backend/ # Main Django project directory
│ ├── asgi.py # ASGI configuration for Channels
│ ├── settings.py # Django settings
│ ├── urls.py # URL configuration
│ └── wsgi.py # WSGI configuration
├── manage.py # Django management script
├── requirements.txt # Project dependencies
└── README.md # This file


## API Endpoints

(A detailed list of API endpoints with request/response examples would be included here.)

### Users
-   `GET /users/`: List all users.
-   `GET /users/{id}/`: Get a specific user.
-   `GET /users/in_team/?team_id={team_id}`: Get users in a team
-   `GET /users/in_channel/?channel_id={channel_id}`: Get users in a channel
-   `GET /users/interacted/?team_id={team_id}`: Get users with whom the current user has interacted within a team

### Teams
-   `GET /teams/`: List teams for the authenticated user.
-   `POST /teams/`: Create a new team.
-   `GET /teams/{id}/`: Get a specific team.
-   `PUT /teams/{id}/`: Update a team.
-   `DELETE /teams/{id}/`: Delete a team.
-   `POST /teams/{id}/add_member/`: Add a member to a team.
-   `POST /teams/{id}/create_invitation/`: Create invitation
-   `POST /teams/join_via_invitation/`: Join team via invitation
-   `GET /teams/{id}/invitations/`: List invitations for a team
-   `POST /teams/{id}/revoke_invitation/`: Revoke invitation for a team

### Channels

-   `GET /channels/`: List channels for the authenticated user's teams.
-   `POST /channels/`: Create a new channel.
-   `GET /channels/{id}/`: Get a specific channel.
-   `PUT /channels/{id}/`: Update a channel.
-   `DELETE /channels/{id}/`: Delete a channel.
-   `GET /channels/{id}/messages/`: Get messages for a channel.
-   `POST /channels/team_id/`: List channels for the requested team id.

### Messages

-   `GET /messages/`: List messages for channels the authenticated user is a part of, or direct messages to/from the user.
-   `POST /messages/`: Create a new message (either channel or direct).
-   `GET /messages/{id}/`: Get a specific message.
-   `PUT /messages/{id}/`: Update a message.
-   `DELETE /messages/{id}/`: Delete a message.

## Channels Consumers

The `ChatConsumer` class in `chat/consumers.py` handles WebSocket connections for real-time chat functionality. It uses Django Channels to manage WebSocket connections and Redis as a channel layer.

**Key Functionality:**

-   **Connection Management:**
    -   `connect()`:  Accepts the WebSocket connection if the user is authenticated. Adds the user to personal, team, and channel groups in the channel layer for targeted message delivery.
    -   `disconnect()`: Removes the user from all groups when the WebSocket connection is closed.

-   **Message Handling:**
    -   `receive_json()`:  Receives JSON messages from the WebSocket, determines the message type, and calls the appropriate handler function. It handles various message types, including:
        -   `channel_message`:  For sending messages to a channel.
        -   `direct_message`: For sending direct messages to a user.
        -   `team_notification`: For sending notifications to a team.
        -   `create_channel`: For creating a new channel within a team.
        -   `add_team_member`: For adding a new member to a team.
        -   `get_channel_messages`, `get_direct_messages`, `get_team_channels`, `get_team_members`, `get_interacted_users`: For fetching data and sending it back to the client.
        -   `delete_message`: For deleting a message (channel or direct).
        -    `reaction`: For handling reactions to messages

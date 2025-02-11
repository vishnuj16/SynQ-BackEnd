from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model
from urllib.parse import parse_qs
import logging
from jwt import decode as jwt_decode

from django.conf import settings

logger = logging.getLogger(__name__)

class JwtAuthMiddleware(BaseMiddleware):
    def __init__(self, inner):
        super().__init__(inner)  # Ensure correct BaseMiddleware initialization

    async def __call__(self, scope, receive, send):
        logger.info("Middleware is running")
        # breakpoint()
        headers = dict(scope.get("headers", []))
        query_string = scope.get('query_string', b'').decode()
        query_params = parse_qs(query_string)

        token = None
        logger.info(f"Headers: {headers}")
        # breakpoint()

        print("HI")

        if b'authorization' in headers:
            print("If condition")
            auth_header = headers[b'authorization'].decode()
            if auth_header.startswith("Bearer "):
                token = auth_header.split("Bearer ")[1]
                logger.info(f"Token: {token}")
                print("Token: ", token)

        if not token:
            token = query_params.get('token', [None])[0]
            if token:
                print(f"Toke recieved from Query Params : {token}")

        if token:
            data = jwt_decode(token, settings.SIMPLE_JWT["SIGNING_KEY"], algorithms=["HS256"])
            print("Data: ", data)
            user = await self.get_user(data['user_id'])
            scope['user'] = user if user else AnonymousUser()
        else:
            scope['user'] = AnonymousUser()

        # breakpoint()
        return await super().__call__(scope, receive, send)

    @database_sync_to_async
    def get_user(self, user_id):
        User = get_user_model()
        try:
            return User.objects.get(id=user_id)
        except (User.DoesNotExist, Exception):
            breakpoint()
            return AnonymousUser()

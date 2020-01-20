import os
import hashlib
from uuid import uuid4
from datetime import datetime

import aiohttp

from fire_document import Document
from fire_odm import MongoDBModel, Field
from fire_api import JSONAPIMixin, TimestampMixin


class User(MongoDBModel, JSONAPIMixin, TimestampMixin):

    __rate__ = ( 10, 'secondly' )

    __acl__ = {
        'self': ['read', 'update', 'delete'],
        'administrator': ['read_all', 'read', 'update'],
        'other': ['read'],
        'unauthorized': ['create']
    }

    __get__ = {
        'username': ['self'],
        'password': [ ],
        'groups': ['administrator'],
        'email': ['self', 'administrator'],
        'secret': [ ],
        'key': ['self'],
    }

    __set__ = {
        'username': ['self', 'administrator', 'unauthorized'],
        'password': ['self', 'unauthorized'],
        'email': ['self', 'administrator', 'unauthorized'],
        'groups': ['administrator'],
        'secret': [ ],
        'key': ['self'],
    }

    __database__ = {
        'name': 'fire-server'
    }

    username = Field(required=True)
    password = Field(required=True, validated='validate_password', computed='encrypt_password', validated_before_computed=True)
    email = Field(required=True)

    secret = Field()
    key = Field(validated='confirm_key')

    groups = Field(type=list, computed=lambda: [ 'users' ], computed_empty=True)

    created = Field(type='timestamp', computed=lambda: datetime.now(), computed_empty=True, computed_type=True)

    async def send_confirmation_email(self):

        async with aiohttp.ClientSession() as session:

            url = f'{os.getenv("FIRE_MAILGUN_URL")}/messages'

            data = {
                'from': os.getenv('FIRE_MAILGUN_FROM', 'Fire Server <fire@server.com>'),
                'to': [ self.email ],
                'subject': 'Account Confirmation',
                'text': f'{hashlib.sha256(self.secret.encode()).hexdigest()}'
            }

            auth = aiohttp.BasicAuth('api', os.getenv('FIRE_MAILGUN_API_KEY'))

            async with session.request('POST', url, auth=auth, data=data) as response:
                json = Document(await response.json())
                if json.message == '\'to\' parameter is not a valid address. please check documentation':
                    raise Exception('Invalid email address.')
                elif not json.message == 'Queued. Thank you.':
                    raise Exception(f'Failed to send confirmation email: {json.message}')

    async def send_authorization_attempt_email(self):

        async with aiohttp.ClientSession() as session:

            url = f'{os.getenv("FIRE_MAILGUN_URL")}/messages'

            data = {
                'from': os.getenv('FIRE_MAILGUN_FROM', 'Fire Server <fire@server.com>'),
                'to': [ self.email ],
                'subject': 'Account Confirmation',
                'text': f'A key authorization attempt has failed.'
            }

            auth = aiohttp.BasicAuth('api', os.getenv('FIRE_MAILGUN_API_KEY'))

            async with session.request('POST', url, auth=auth, data=data) as response:
                json = Document(await response.json())
                if json.message == '\'to\' parameter is not a valid address. please check documentation':
                    raise Exception('Invalid email address.')
                elif not json.message == 'Queued. Thank you.':
                    raise Exception(f'Failed to send confirmation email: {json.message}')

    async def on_create(self, token):

        if await self.find_one({ 'username': self.username }):
            raise Exception(f'Username {self.username} already exists.')

        if await self.find_one({ 'email': self.email }):
            raise Exception(f'Email {self.email} already taken.')

        self.secret = str(uuid4())
        #await self.send_confirmation_email()

    async def on_update(self, token, attributes):

        username = attributes.get('username')
        user = await self.find_one({ 'username': username })
        if username and user and not (user.id == self.id):
            raise Exception(f'Username {username} already exists.')

        email = attributes.get('email')
        user = await self.find_one({ 'email': email })
        if email:
            if user and not (user.id == self.id):
                raise Exception(f'Email {email} already taken.')
            elif not (email == self.email):
                self.key = None
                self.secret = str(uuid4())
                #await self.send_confirmation_email()

    def validate_password(self, password):
        if len(self.password) < 8:
            raise Exception('Password length must be at least 8 characters.')

    def encrypt_password(self):
        if self.password == 'hashed-':
            raise Exception('Invalid password.')

        if self.password.startswith('hashed-'):
            return self.password

        return f'hashed-{hashlib.sha256(self.password.encode()).hexdigest()}'

    def confirm_key(self, key):
        if not key == 'None' and key and not \
            (key == hashlib.sha256(self.secret.encode()).hexdigest()):
                raise Exception('Invalid key.')

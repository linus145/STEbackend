import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async

# Lazy imports to ensure Django initializes correctly inside app lifecycle
@sync_to_async
def save_message_async(room_id, user_id, text):
    from chat.services import ChatService
    msg = ChatService.save_message(room_id=room_id, sender_id=user_id, text=text)
    if msg:
        return {
            'id': str(msg.id),
            'text': msg.text,
            'sender_id': str(msg.sender.id),
            'sender_email': msg.sender.email,
            'created_at': msg.created_at.isoformat()
        }
    return None

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'chat_{self.room_id}'

        # Ensure user is authenticated, else block WebSocket immediately
        if not self.scope.get('user') or not self.scope['user'].is_authenticated:
            await self.close()
            return

        # Join room group natively
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        # Gracefully exit room
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Receive incoming websocket frames
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message_text = text_data_json.get('message', '')
        user = self.scope["user"]

        if message_text.strip():
            # Drop purely into Service Layer asynchronously 
            msg_data = await save_message_async(self.room_id, user.id, message_text)

            if msg_data:
                # Blast message back to all users in the specific chat layer
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_message',
                        'message_payload': msg_data
                    }
                )

    # Process events beamed from the group
    async def chat_message(self, event):
        message_payload = event['message_payload']

        # Push to the local WebSocket cleanly
        await self.send(text_data=json.dumps({
            'message': message_payload
        }))

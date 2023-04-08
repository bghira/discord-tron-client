import time
from PIL import Image


class WebsocketMessage:
    def __init__(self, message_type: str, module_name: str, module_command, data=None, arguments=None):
        self._message_type = message_type
        self._module_name = module_name
        self._module_command = module_command
        self._timestamp = time.time()
        self._data = data or {"images": []}
        self._arguments = arguments or {}


    @property
    def message_type(self):
        return self._message_type

    @message_type.setter
    def message_type(self, value: str):
        self._message_type = value

    @property
    def module_name(self):
        return self._module_name

    @module_name.setter
    def module_name(self, value):
        self._module_name = value

    @property
    def module_command(self):
        return self._module_command

    @module_command.setter
    def module_command(self, value):
        self._module_command = value

    @property
    def timestamp(self):
        return self._timestamp

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, value):
        self._data = value

    @property
    def arguments(self):
        return self._arguments

    @arguments.setter
    def arguments(self, value):
        self._arguments = value

    @staticmethod
    def encode_image_to_base64(image_path: str) -> str:
        import base64
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        return encoded_string

    def add_image(self, image: Image):
        if "images" not in self.data:
            self.data["images"] = []
        self.data["images"].append(self.encode_image_to_base64(image))

    def to_dict(self):
        return {
            "message_type": self.message_type,
            "module_name": self.module_name,
            "module_command": self.module_command,
            "timestamp": self.timestamp,
            "data": self.data,
            "arguments": self.arguments
        }
    
    def to_json(self):
        import json
        return json.dumps(self.to_dict())
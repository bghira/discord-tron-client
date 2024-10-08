import time, logging
from PIL import Image
from discord_tron_client.classes.app_config import AppConfig

config = AppConfig()
logger = logging.getLogger(__name__)
logger.setLevel(config.get_log_level())


class WebsocketMessage:
    def __init__(
        self, message_type: str, module_name: str, module_command, data={}, arguments={}
    ):
        self.message_type = message_type
        self.module_name = module_name
        self.module_command = module_command
        self.timestamp = time.time()
        self.data = data
        self.base_arguments = arguments
        self.arguments = None

    def update(
        self,
        message_type=None,
        module_name=None,
        module_command=None,
        data=None,
        arguments=None,
    ):
        logging.debug(
            f"Calling update on message: {message_type}, {module_name}, {module_command}, {data}, {arguments}"
        )
        if message_type:
            self.message_type = message_type
        if module_name:
            self.module_name = module_name
        if module_command:
            self.module_command = module_command
        if data:
            self.data = data
        if arguments:
            self.arguments = arguments
            logging.debug(f"Updated arguments: {self.arguments}")

    @staticmethod
    def encode_image_to_base64(image: Image) -> str:
        import io
        import base64

        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode("utf-8")

    def add_image(self, image: Image):
        if "images" not in self.data:
            self.data["images"] = []
        self.data["images"].append(self.encode_image_to_base64(image))

    def to_dict(self):
        # Check if "arguments" property exists, and use it. Otherwise, use base_arguments:
        if self.arguments is None:
            logging.debug("Addon arguments not found. Using constructor args.")
            self.arguments = self.base_arguments
        output = {
            "message_type": self.message_type,
            "module_name": self.module_name,
            "module_command": self.module_command,
            "timestamp": self.timestamp,
            "data": self.data,
            "arguments": self.arguments,
            "base_arguments": self.base_arguments,
        }
        logger.debug(f"Returning output: {output}")
        return output

    def to_json(self):
        import json

        return json.dumps(self.to_dict())

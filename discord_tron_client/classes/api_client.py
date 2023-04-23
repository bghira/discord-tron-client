import logging, json, requests, sys, os, io
from discord_tron_client.classes.auth import Auth
from discord_tron_client.classes.app_config import AppConfig
from PIL import Image

class ApiClient:
    def __init__(self, auth: Auth, config: AppConfig):
        self.auth = auth
        self.config = config
        self.base_url = config.get_master_url()
        self.verify_ssl = config.verify_master_ssl()
        self.api_key = config.get_master_api_key()
        self.headers = self._set_auth_header()
        
    def get(self, endpoint: str, params: dict = None):
        if params is None:
            params = {}
        url = self.base_url + endpoint
        params["api_key"] = self.api_key
        params["access_token"] = self.auth.get()
        response = requests.get(url, params=params, verify=self.verify_ssl)
        return self.handle_response(response)

    def put(self, endpoint: str, params: dict = None):
        if params is None:
            params = {}
        url = self.base_url + endpoint
        params["api_key"] = self.api_key
        params["access_token"] = self.auth.get()
        response = requests.put(url, params=params, verify=self.verify_ssl)
        return self.handle_response(response)
    
    def post(self, endpoint: str, params: dict = None, files: dict = None):
        if params is None:
            params = {}
        headers = self._set_auth_header()
        url = self.base_url + endpoint
        response = requests.post(url, params=params, verify=self.verify_ssl, files=files, headers=headers)
        return self.handle_response(response)
    
    def send_file(self, endpoint: str, file_path: str):
        with open(file_path, "rb") as f:
            response = requests.post(endpoint, files={"file": f})
        return response
    
    async def send_pil_image(self, endpoint: str, image: Image):
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        import asyncio
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            AppConfig.get_image_worker_thread(),  # Use a dedicated image processing thread worker.
            self.post,
            endpoint,
            None,
            {"image": buffer}
        )
        return response
    
    def send_buffer(self, endpoint: str, buffer: io.BytesIO):
        response = self.post(endpoint, files={"file": buffer})
        return response
    
    def handle_response(self, response):
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception("Error: {}".format(response.text))
    
    def _set_auth_header(self) -> dict:
        # We need the token from self.auth.get() to be set as the Authorization header using the Bearing token type
        current_ticket = self.auth.get()
        return { "Authorization": f"Bearer {current_ticket['access_token']}" }
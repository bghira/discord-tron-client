from discord_tron_client.classes.app_config import AppConfig
from discord_tron_client.message.discord import DiscordMessage
from discord_tron_client.classes.debug import clean_traceback
from discord_tron_client.classes.uploader import Uploader
import logging, asyncio
config = AppConfig()

class BarkRunner:
    def __init__(self, bark_driver):
        self.driver = bark_driver
        self.sample_rate = None

    def generate(self, prompt, user_config):
        try:
            if config.is_bark_enabled():
                self.driver.load_model()
        except Exception as e:
            logging.error(f"Could not load Bark driver: {e}")
        audio, self.sample_rate = self.driver.generate(prompt, user_config)
        
        return audio

    def usage(self):
        driver_usage = self.driver.get_usage()
        if driver_usage is None:
            return None
        time_duration = -1
        if "time_duration" in driver_usage:
            time_duration = driver_usage["time_duration"]
        driver_details = self.driver.details() or "`Unknown Bark driver`"
        output_text = f"`{int(time_duration)} seconds`"
        if "total_token_count" in driver_usage:
            output_text = f"{output_text} using `{driver_usage['total_token_count']} tokens`"
        output_text = f"{output_text} via {driver_details}"
        return output_text

    async def generate_handler(self, payload, websocket):
        # We extract the features from the payload and pass them onto the actual generator
        user_config = payload["config"]
        prompt = payload["prompt"]
        logging.debug(f"BarkRunner generate_handler received prompt {prompt}")
        thinking_msg = "Thinking!"
        if not self.driver.loaded:
            thinking_msg = "Loading model first! We may have to download it. This could take a while, but subsequent requests will be faster!"
        discord_msg = DiscordMessage(websocket=websocket, context=payload["discord_first_message"], module_command="edit", message=thinking_msg)
        websocket = AppConfig.get_websocket()
        await websocket.send(discord_msg.to_json())
        try:
            loop = asyncio.get_event_loop()
            output_audio = await loop.run_in_executor(
                AppConfig.get_image_worker_thread(),  # Use the image processing thread worker.
                self.generate,
                prompt,
                user_config
            )
            # Try uploading via the HTTP API
            api_client = AppConfig.get_api_client()
            uploader = Uploader(api_client=api_client, config=config)
            logging.debug(f"Received result from TTS engine: {output_audio}, {self.sample_rate}")
            url_list = await uploader.audio(output_audio, self.sample_rate)
            usage = self.usage()
            discord_msg = DiscordMessage(websocket=websocket, context=payload["discord_first_message"], module_command="send", message=f'<@{payload["discord_context"]["author"]["id"]}>: ' + '`' + prompt + f'`\nUsage stats: {usage}', audio_url=url_list)
            websocket = AppConfig.get_websocket()
            await websocket.send(discord_msg.to_json())

            discord_msg = DiscordMessage(websocket=websocket, context=payload["discord_first_message"], module_command="delete")
            websocket = AppConfig.get_websocket()
            await websocket.send(discord_msg.to_json())

            discord_msg = DiscordMessage(websocket=websocket, context=payload["discord_context"], module_command="delete")
            websocket = AppConfig.get_websocket()
            await websocket.send(discord_msg.to_json())

        except Exception as e:
            import traceback
            logging.error(f"Received an error in BarkRunner.generate_handler: {e}, traceback: {clean_traceback(traceback.format_exc())}")
            discord_msg = DiscordMessage(websocket=websocket, context=payload["discord_first_message"], module_command="edit", message=f"We pooped the bed when generating your audio! {e}, traceback: {await clean_traceback(traceback.format_exc())})")
            websocket = AppConfig.get_websocket()
            await websocket.send(discord_msg.to_json())
            raise e
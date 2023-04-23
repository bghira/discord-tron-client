from discord_tron_client.classes.app_config import AppConfig
from discord_tron_client.message.discord import DiscordMessage
from discord_tron_client.classes.debug import clean_traceback
import logging, asyncio
config = AppConfig()

class LlamaRunner:
    def __init__(self, llama_driver):
        self.driver = llama_driver
        self.driver.load_model()
        
    def predict(self, prompt, user_config):
        return self.driver.predict(prompt, user_config)
    
    async def predict_handler(self, payload, websocket):
        # We extract the features from the payload and pass them onto the actual generator
        user_config = payload["config"]
        prompt = payload["prompt"]
        logging.debug(f"LlamaRunner predict_handler received prompt {prompt}")
        discord_msg = DiscordMessage(websocket=websocket, context=payload["discord_first_message"], module_command="edit", message="Thinking!")
        websocket = AppConfig.get_websocket()
        await websocket.send(discord_msg.to_json())
        try:
            loop = asyncio.get_event_loop()
            loop_return = await loop.run_in_executor(
                AppConfig.get_image_worker_thread(),  # Use a dedicated image processing thread worker.
                self.predict,
                prompt,
                user_config
            )
            logging.debug(f"LlamaRunner predict_handler received result {loop_return}")
            discord_msg = DiscordMessage(websocket=websocket, context=payload["discord_first_message"], module_command="send", message=f'<@{payload["discord_context"]["author"]["id"]}>: ' + '`' + prompt + '`, ...' + loop_return)
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
            logging.error(f"Received an error in LlamaRunner.predict_handler: {e}, traceback: {clean_traceback(traceback.format_exc())}")
            discord_msg = DiscordMessage(websocket=websocket, context=payload["discord_first_message"], module_command="edit", message="We pooped the bed!")
            websocket = AppConfig.get_websocket()
            await websocket.send(discord_msg.to_json())
            raise e
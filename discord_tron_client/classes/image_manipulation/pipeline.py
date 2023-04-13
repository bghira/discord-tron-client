import logging
import sys
import torch
import traceback
import time
import asyncio
from tqdm import tqdm
from discord_tron_client.classes.app_config import AppConfig
from discord_tron_client.classes.image_manipulation.resolution import ResolutionManager
from discord_tron_client.classes.tqdm_capture import TqdmCapture
from discord_tron_client.classes.discord_progress_bar import DiscordProgressBar
from discord_tron_client.message.discord import DiscordMessage
from PIL import Image

class PipelineRunner:
    def __init__(
        self,
        model_manager,
        pipeline_manager,
        app_config: AppConfig,
        user_config: dict,
        discord_msg,
        websocket
    ):
        # General AppConfig() object access.
        self.config = app_config
        self.seed = None
        main_loop = asyncio.get_event_loop()
        if main_loop is None:
            raise Exception("AppConfig.main_loop is not set!")
        # The received user_config item from TRON master.
        self.user_config = user_config
        # Managers.
        self.model_manager = model_manager
        self.pipeline_manager = pipeline_manager
        # A message template for the WebSocket events.
        self.progress_bar_message = DiscordMessage(
            websocket=websocket,
            context=discord_msg,
            module_command="edit"
        )
        # An object to manage a progress bar for Discord.
        self.progress_bar = DiscordProgressBar(
            websocket=websocket,
            websocket_message=self.progress_bar_message,
            progress_bar_steps=100,
            progress_bar_length=20,
            discord_first_message=discord_msg
        )
        self.tqdm_capture = TqdmCapture(self.progress_bar, main_loop)
        self.websocket = websocket

    async def _prepare_pipe_async(
        self,
        model_id: int,
        img2img: bool = False,
        promptless_variation: bool = False,
        SAG: bool = False
    ):
        loop = asyncio.get_event_loop()
        loop_return = await loop.run_in_executor(
            AppConfig.get_image_worker_thread(),  # Use a dedicated image processing thread worker.
            self._prepare_pipe,
            model_id,
            img2img,
            promptless_variation,
            SAG
        )
        return loop_return

    def _prepare_pipe(
        self,
        model_id: int,
        img2img: bool = False,
        promptless_variation: bool = False,
        SAG: bool = False
    ):
        logging.info(f"Retrieving pipe for model {model_id}")
        if not promptless_variation:
            pipe = self.pipeline_manager.get_pipe(model_id, img2img, SAG)
        else:
            pipe = self.pipeline_manager.get_variation_pipe(model_id)
        logging.info("Copied pipe to the local context")
        return pipe

    async def _generate_image_with_pipe_async(
        self,
        pipe,
        prompt: str,
        side_x: int,
        side_y: int,
        steps: int,
        negative_prompt: str,
        user_config: dict,
        image: Image = None,
        promptless_variation: bool = False,
        SAG: bool = False
    ):
        loop = asyncio.get_event_loop()
        loop_return = await loop.run_in_executor(
            AppConfig.get_image_worker_thread(),  # Use a dedicated image processing thread worker.
            self._generate_image_with_pipe,
            pipe,
            prompt,
            side_x,
            side_y,
            steps,
            negative_prompt,
            user_config,
            image,
            promptless_variation
        )
        delete_progress_bar = DiscordMessage(websocket=self.websocket, context=self.progress_bar_message.context, module_command="delete")
        for attempt in range(1, 6):
            if not self.websocket or not hasattr(self.websocket, "open") or self.websocket.open != True:
                logging.warn("WebSocket connection is not open. Retrieving fresh instance.")
                self.websocket = AppConfig.get_websocket()
                await asyncio.sleep(2)
            else:
                logging.debug("WebSocket connection is open. Continuing.")
                break
        await self.websocket.send(delete_progress_bar.to_json())
        return loop_return

    def _generate_image_with_pipe(
        self,
        pipe,
        prompt: str,
        side_x: int,
        side_y: int,
        steps: int,
        negative_prompt: str,
        user_config: dict,
        image: Image = None,
        promptless_variation: bool = False
    ):
        try:
            guidance_scale = user_config.get("guidance_scale", 7.5)
            guidance_scale = min(guidance_scale, 20)

            SAG = user_config.get("enable_sag", True)
            if SAG:
                sag_scale = user_config.get("sag_scale", 0.75)
                sag_scale = min(sag_scale, 20)

            self.seed = user_config.get("seed", int(time.time()))
            generator = torch.manual_seed(self.seed)

            with torch.no_grad():
                with tqdm(total=steps, ncols=100, file=self.tqdm_capture) as pbar:
                    new_image = self._run_pipeline(
                        pipe,
                        prompt,
                        side_x,
                        side_y,
                        steps,
                        negative_prompt,
                        guidance_scale,
                        generator,
                        SAG,
                        sag_scale,
                        user_config,
                        image,
                        promptless_variation
                    )

            return new_image
        except Exception as e:
            logging.error(f"Error while generating image: {e}\n{traceback.format_exc()}")

    def _run_pipeline(
        self,
        pipe,
        prompt: str,
        side_x: int,
        side_y: int,
        steps: int,
        negative_prompt: str,
        guidance_scale: float,
        generator,
        SAG: bool,
        sag_scale: float,
        user_config: dict,
        image: Image = None,
        promptless_variation: bool = False
    ):
        if not promptless_variation and image is None and not SAG:
            new_image = pipe(
                prompt=prompt,
                height=side_y,
                width=side_x,
                num_inference_steps=int(float(steps)),
                negative_prompt=negative_prompt,
                guidance_scale=guidance_scale,
                generator=generator,
            ).images[0]
        elif SAG:
            new_image = pipe(
                prompt=prompt,
                height=side_y,
                width=side_x,
                num_inference_steps=int(float(steps)),
                negative_prompt=negative_prompt,
                guidance_scale=guidance_scale,
                generator=generator,
                sag_scale=sag_scale,
            ).images[0]
        elif image is not None:
            new_image = pipe(
                prompt=prompt,
                image=image,
                strength=user_config["strength"],
                num_inference_steps=int(float(steps)),
                negative_prompt=negative_prompt,
                guidance_scale=guidance_scale,
                generator=generator,
            ).images[0]
        elif promptless_variation:
            new_image = pipe(
                height=side_y,
                width=side_x,
                num_inference_steps=int(float(steps)),
                guidance_scale=guidance_scale,
                generator=generator,
            ).images[0]
        else:
            raise Exception("Invalid combination of parameters for image generation")

        return new_image

    async def generate_image(
        self,
        model_id: int,
        prompt: str,
        side_x: int,
        side_y: int,
        steps: int,
        negative_prompt: str = "",
        img2img: bool = False,
        image: Image = None,
        promptless_variation: bool = False
    ):
        pipe = await self._prepare_pipe_async(
            model_id,
            img2img,
            promptless_variation,
            self.user_config.get("enable_sag", True)
        )

        new_image = await self._generate_image_with_pipe_async(
            pipe,
            prompt,
            side_x,
            side_y,
            steps,
            negative_prompt,
            self.user_config,
            image,
            promptless_variation
        )

        return new_image
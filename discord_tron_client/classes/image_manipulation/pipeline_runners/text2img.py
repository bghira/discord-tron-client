from discord_tron_client.classes.image_manipulation.pipeline_runners.base_runner import (
    BasePipelineRunner,
)
from discord_tron_client.classes.app_config import AppConfig
from diffusers import ConsistencyDecoderVAE
import logging, torch

config = AppConfig()


class Text2ImgPipelineRunner(BasePipelineRunner):
    def __init__(self, pipeline):
        self.pipeline = pipeline
        # if hasattr(pipeline, 'vae'):
        #     pipeline.vae = ConsistencyDecoderVAE.from_pretrained("openai/consistency-decoder").to(dtype=torch.bfloat16, device="cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu")

    def __call__(self, **args):
        # Get user_config and delete it from args, it doesn't get passed to the pipeline
        user_config = args.get("user_config", None)
        del args["user_config"]
        if "pooled_prompt_embeds" in args:
            del args["pooled_prompt_embeds"]
        if "negative_pooled_prompt_embeds" in args:
            del args["negative_pooled_prompt_embeds"]
        # if user_config.get("prompt_weighting", True) and config.enable_compel():
        #     # Remove unwanted arguments for this condition
        #     for unwanted_arg in ["prompt", "negative_prompt"]:
        #         if unwanted_arg in args:
        #             del args[unwanted_arg]
        #     logging.debug(f'Removing unwanted args: {unwanted_arg}')
        # else:
        # Remove unwanted arguments for this condition
        for unwanted_arg in ["prompt_embeds", "negative_prompt_embeds"]:
            if unwanted_arg in args:
                del args[unwanted_arg]
        logging.debug(f"Removing unwanted args: {unwanted_arg}")

        # Convert specific arguments to desired types
        if "num_inference_steps" in args:
            args["num_inference_steps"] = int(float(args["num_inference_steps"]))
        if "guidance_scale" in args:
            args["guidance_scale"] = float(args["guidance_scale"])
        if "guidance_rescale" in args:
            args["guidance_rescale"] = float(args["guidance_rescale"])
        # Call the pipeline with arguments and return the images
        logging.debug(f"Calling pipeline with args: {args}")
        return self.pipeline(**args).images

from discord_tron_client.classes.image_manipulation.pipeline_runners.base_runner import (
    BasePipelineRunner,
)
from diffusers import DiffusionPipeline
from PIL import Image
import logging


class DeepFloydPipelineRunner(BasePipelineRunner):
    def __init__(self, stage1, pipeline_manager, diffusion_manager):
        self.stage1 = stage1  # DeepFloyd/IF-I-XL-v1.0
        self.stage2 = None  # DeepFloyd/IF-II-L-v1.0
        self.stage3 = None  # Upscaler
        self.pipeline_manager = pipeline_manager
        self.diffusion_manager = diffusion_manager
        self.safety_modules = {
            "feature_extractor": self.stage1.feature_extractor,
            "safety_checker": None,
            "watermarker": None,
        }

    def _invoke_sdxl(self, user_config: dict, prompt: str, negative_prompt: str, image: Image):
        logging.debug(f'Upscaling DeepFloyd output using SDXL refiner.')
        return self.diffusion_manager._refiner_pipeline(
            images=[
                image
            ],
            user_config=user_config,
            prompt=prompt,
            negative_prompt=negative_prompt,
            random_seed=False,
            denoising_start=None
        )

    def _setup_stage2(self, user_config):
        stage2_model = "DeepFloyd/IF-II-L-v1.0"
        scheduler_config = {}  # This isn't really used anymore.
        if self.stage2 is not None:
            logging.info(f"Keeping existing {stage2_model} model.")
            return
        self.stage2 = self.pipeline_manager.get_pipe(
            model_id=stage2_model,
            user_config=user_config,
            scheduler_config=scheduler_config,
        )
        self.stage2.enable_model_cpu_offload()
        return

    def _invoke_stage2(
        self,
        image: Image,
        user_config,
        prompt_embeds,
        negative_embeds,
        width=64,
        height=64,
    ):
        self._setup_stage2(user_config)
        s2_width = width * 4
        s2_height = height * 4
        return self.stage_2(
            image=image,
            prompt_embeds=prompt_embeds,
            negative_prompt_embeds=negative_embeds,
            output_type="pt",
            width=s2_width,
            height=s2_height,
        ).images

    def _setup_stage3(self, user_config):
        stage3_model = "stabilityai/stable-diffusion-x4-upscaler"
        scheduler_config = {}  # This isn't really used anymore.
        if self.stage3 is not None:
            logging.info(f"Keeping existing {stage3_model} model.")
            return
        self.stage3 = self.pipeline_manager.get_pipe(
            model_id=stage3_model,
            user_config=user_config,
            scheduler_config=scheduler_config,
        )
        self.stage3.enable_model_cpu_offload()
        return

    def _invoke_stage3(self, prompt: str, image: Image, user_config: dict, width: int, height: int):
        user_strength = user_config.get("deepfloyd_stage3_strength", 1.0)
        s3_width = width * 4 * 4
        s3_height = height * 4 * 4
        return self.stage3(
            prompt=prompt,
            image=image,
            width=s3_width,
            height=s3_height,
            noise_level=(100 * user_strength),
        ).images

    def _invoke_stage1(
        self, prompt_embed, negative_prompt_embed, user_config, width=64, height=64
    ):
        return self.stage1(
            prompt_embeds=prompt_embed,
            negative_prompt_embeds=negative_prompt_embed,
            generator=self.pipeline_manager._get_generator(user_config),
            output_type="pt",
            width=width,
            height=height,
        ).images

    def _embeds(self, prompt: str, negative_prompt: str):
        return self.stage1.encode_prompt(prompt, negative_prompt)

    def _get_stage1_resolution(self, user_config: dict):
        # Grab the aspect ratio of the user_config['resolution']['width']xuser_config['resolution']['height'],
        # and then use that to ensure that the smaller side is 64px, while the larger side is 64px * aspect_ratio.
        # This has to support portrait or landscape, as well as square images.
        width = user_config.get("resolution", {}).get("width", 768)
        height = user_config.get("resolution", {}).get("height", 768)
        aspect_ratio = width / height
        if width > height:
            # Landscape
            width = 64
            height = int(width * aspect_ratio)
        elif height > width:
            # Portrait
            height = 64
            width = int(height * aspect_ratio)
        else:
            # Square
            width = 64
            height = 64
        return width, height

    def __call__(self, **args):
        # Get user_config and delete it from args, it doesn't get passed to the pipeline
        user_config = args.get("user_config", None)
        del args["user_config"]

        # Grab prompt embeds from T5.
        prompt_embeds, negative_embeds = self._embeds(
            args.get("prompt", ""), args.get("negative_prompt", "")
        )

        logging.debug(f"Generating stage 1 output.")
        width, height = self._get_stage1_resolution(user_config)
        stage1_output = self._invoke_stage1(
            prompt_embed=prompt_embeds,
            negative_prompt_embed=negative_embeds,
            width=width,
            height=height,
        )
        logging.debug(f"Generating DeepFloyd Stage2 output.")
        stage2_output = self._invoke_stage2(
            prompt=args.get("prompt", ""),
            image=stage1_output,
            user_config=user_config,
            prompt_embeds=prompt_embeds,
            negative_embeds=negative_embeds,
            width=width,
            height=height,
        )
        use_x4_upscaler = user_config.get("use_df_x4_upscaler", False)
        if use_x4_upscaler:
            logging.debug(f"Generating DeepFloyd Stage3 output using x4 upscaler.")
            stage3_output = self._invoke_stage3(
                prompt=args.get("prompt", ""),
                image=stage2_output,
                user_config=user_config,
                width=width,
                height=height
            )
            return stage3_output
        elif user_config.get('latent_refiner', True):
            logging.debug(f"Generating DeepFloyd Stage3 output using latent refiner.")
            stage3_output = self._invoke_sdxl(
                prompt=args.get("prompt", ""),
                image=stage2_output,
                user_config=user_config,
                width=width,
                height=height
            )
            return stage3_output
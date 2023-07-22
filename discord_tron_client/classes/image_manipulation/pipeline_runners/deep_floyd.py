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

    def _invoke_sdxl(self, user_config: dict, prompt: str, negative_prompt: str, images: Image):
        logging.debug(f'Upscaling DeepFloyd output using SDXL refiner.')
        # Upscale using PIL, by 4:
        if type(images) != list:
            images = [images]
        idx = 0
        for image in images:
            width = image.width * 4
            height = image.height * 4
            images[idx] = image.resize((width, height), Image.LANCZOS)
            idx += 1
        return self.diffusion_manager._refiner_pipeline(
            images=images,
            user_config=user_config,
            prompt=prompt,
            negative_prompt=negative_prompt,
            random_seed=False,
            denoising_start=None
        )

    def _setup_stage2(self, user_config):
        stage2_model = "DeepFloyd/IF-II-L-v1.0"
        logging.debug(f'Configuring DF-IF Stage II Pipeline: {stage2_model}')
        scheduler_config = {}  # This isn't really used anymore.
        if self.stage2 is not None:
            logging.info(f"Keeping existing {stage2_model} model with {type(self.stage2)} pipeline.")
            return
        self.stage2 = self.pipeline_manager.get_pipe(
            model_id=stage2_model,
            user_config=user_config,
            scheduler_config=scheduler_config,
            custom_text_encoder=-1
        )

    def _invoke_stage2(
        self,
        image: Image,
        user_config,
        prompt_embeds,
        negative_embeds,
        width=64,
        height=64,
        output_type="pt",
    ):
        self._setup_stage2(user_config)
        s2_width = width * 4
        s2_height = height * 4
        logging.debug(f'Generating DeepFloyd Stage2 output at {s2_width}x{s2_height}.')
        stage2_result = self.stage2(
            image=image,
            prompt_embeds=prompt_embeds,
            negative_prompt_embeds=negative_embeds,
            output_type=output_type,
            width=s2_width,
            height=s2_height,
            num_images_per_prompt=4,
            guidance_scale=user_config.get("df_guidance_scale_2", 5.7),
        ).images
        logging.debug(f'Result: {type(stage2_result)}')
        return stage2_result

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
        return

    def _invoke_stage3(self, prompt: str, negative_prompt: str, image: Image, user_config: dict):
        self._setup_stage3(user_config)
        user_strength = user_config.get("deepfloyd_stage3_strength", 1.0)
        return self.stage3(
            prompt=[prompt] * len(image),
            negative_prompt=[negative_prompt] * len(image),
            image=image,
            noise_level=(100 * user_strength),
            guidance_scale=user_config.get("df_guidance_scale_3", 5.6),
        ).images

    def _invoke_stage1(
        self, prompt_embed, negative_prompt_embed, user_config: dict, width=64, height=64
    ):
        return self.stage1(
            prompt_embeds=prompt_embed,
            negative_prompt_embeds=negative_prompt_embed,
            generator=self.diffusion_manager._get_generator(user_config),
            guidance_scale=user_config.get('df_guidance_scale_1', 9.2),
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
        prompt = args.get("prompt", "")
        negative_prompt = args.get("negative_prompt", "")
        prompt_embeds, negative_embeds = self._embeds(
            prompt, negative_prompt
        )
        try:
            logging.debug(f"Generating stage 1 output.")
            width, height = self._get_stage1_resolution(user_config)
            stage1_output = self._invoke_stage1(
                prompt_embed=prompt_embeds,
                negative_prompt_embed=negative_embeds,
                width=width,
                height=height,
                user_config=user_config,
            )
            logging.debug(f"Generating DeepFloyd Stage2 output.")
            stage2_output = self._invoke_stage2(
                image=stage1_output,
                user_config=user_config,
                prompt_embeds=prompt_embeds,
                negative_embeds=negative_embeds,
                width=width,
                height=height,
                output_type="pil" if not user_config.get("use_df_x4_upscaler", False) else "pt"
            )
            use_x4_upscaler = user_config.get("use_df_x4_upscaler", True)
            if use_x4_upscaler:
                logging.debug(f"Generating DeepFloyd Stage3 output using x4 upscaler.")
                stage3_output = self._invoke_stage3(
                    prompt=args.get("prompt", ""),
                    negative_prompt=args.get("negative_prompt", ""),
                    image=stage2_output,
                    user_config=user_config,
                )
                return stage3_output
            logging.debug(f"Generating DeepFloyd Stage3 output using latent refiner.")
            stage3_output = self._invoke_sdxl(
                images=stage2_output,
                user_config=user_config,
                prompt=prompt,
                negative_prompt=negative_prompt
            )
            return stage3_output
        except Exception as e:
            logging.error(f"DeepFloyd pipeline failed: {e}, traceback: {e.__traceback__}")
            raise e
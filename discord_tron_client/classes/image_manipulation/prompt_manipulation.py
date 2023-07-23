from compel import Compel, ReturnedEmbeddingsType
from discord_tron_client.classes.app_config import AppConfig
import logging

config = AppConfig()
# Manipulating prompts for the pipeline.
class PromptManipulation:
    def __init__(self, pipeline, device, use_second_encoder_only: bool = False):
        self.is_valid_pipeline(pipeline)
        self.pipeline = pipeline
        if (self.has_dual_text_encoders(pipeline) and not use_second_encoder_only):
            # SDXL Refiner and Base can both use the 2nd tokenizer/encoder.
            logging.debug(f'Initialising Compel prompt manager with dual encoders.')
            self.compel = Compel(
                tokenizer=[
                    self.pipeline.tokenizer,
                    self.pipeline.tokenizer_2
                ],
                text_encoder=[
                    self.pipeline.text_encoder,
                    self.pipeline.text_encoder_2
                ],
                truncate_long_prompts=True,
                returned_embeddings_type=ReturnedEmbeddingsType.PENULTIMATE_HIDDEN_STATES_NON_NORMALIZED,
                requires_pooled=[
                    False,  # CLIP-L does not produce pooled embeds.
                    True    # CLIP-G produces pooled embeds.
                ]
            )
        elif (self.has_dual_text_encoders(pipeline) and use_second_encoder_only):
            # SDXL Refiner has ONLY the 2nd tokenizer/encoder, which needs to be the only one in Compel.
            logging.debug(f'Initialising Compel prompt manager with just the 2nd text encoder.')
            self.compel = Compel(
                tokenizer=self.pipeline.tokenizer_2,
                text_encoder=self.pipeline.text_encoder_2,
                truncate_long_prompts=True,
                returned_embeddings_type=ReturnedEmbeddingsType.PENULTIMATE_HIDDEN_STATES_NON_NORMALIZED,
                requires_pooled=True
            )
        else:
            # Any other pipeline uses the first tokenizer/encoder.
            logging.debug(f'Initialising the Compel prompt manager with a single text encoder.')
            pipe_tokenizer = self.pipeline.tokenizer
            pipe_text_encoder = self.pipeline.text_encoder
            self.compel = Compel(
                tokenizer=pipe_tokenizer,
                text_encoder=pipe_text_encoder,
                truncate_long_prompts=False,
                returned_embeddings_type=ReturnedEmbeddingsType.LAST_HIDDEN_STATES_NORMALIZED,
            )
    def should_enable(self, pipeline, user_config: dict = None):
        if (type(pipeline).__name__ == "KandinskyV22Pipeline"):
            # KandinskyV22Pipeline doesn't use the prompt manager.
            return False
        if user_config is not None and "DeepFloyd" in user_config.get('model', ''):
            # Does not work for DeepFloyd.
            return False
        return True

    def has_dual_text_encoders(self, pipeline):
        return hasattr(pipeline, "text_encoder_2")

    def is_sdxl_refiner(self, pipeline):
        # SDXL Refiner has the 2nd text encoder, only.
        if self.pipeline.tokenizer is None and hasattr(self.pipeline, "tokenizer_2"):
            return True
        return False

    def is_valid_pipeline(self, pipeline):
        if not hasattr(pipeline, "tokenizer") and not hasattr(
            pipeline, "tokenizer_2"
        ):
            raise Exception(
                f"Cannot use PromptManipulation on a model without a tokenizer."
            )

    def process_long_prompt(self, positive_prompt: str, negative_prompt: str):
        batch_size = config.maximum_batch_size()
        if self.has_dual_text_encoders(self.pipeline):
            logging.debug(f'Running dual encoder Compel pipeline for batch size {batch_size}.')
            # We need to make a list of positive_prompt * batch_size count.
            positive_prompt = [positive_prompt] * batch_size
            conditioning, pooled_embed = self.compel(positive_prompt)
            negative_prompt = [negative_prompt] * batch_size
            negative_conditioning, negative_pooled_embed = self.compel(negative_prompt)
        else:
            logging.debug(f'Running single encoder Compel pipeline.')
            conditioning = self.compel.build_conditioning_tensor(positive_prompt)
            negative_conditioning = self.compel.build_conditioning_tensor(negative_prompt)
        [
            conditioning,
            negative_conditioning,
        ] = self.compel.pad_conditioning_tensors_to_same_length(
            [conditioning, negative_conditioning]
        )
        if self.has_dual_text_encoders(self.pipeline):
            logging.debug(f'Returning pooled embeds along with positive/negative conditionings.')
            return conditioning, negative_conditioning, pooled_embed, negative_pooled_embed
        return conditioning, negative_conditioning

    @staticmethod
    def remove_duplicate_prompts(prompt: str, user_config: dict):
        to_remove = [
            user_config.get('positive_prompt', ''),
            user_config.get('negative_prompt', '')
        ]
        for segment in to_remove:
            if segment in prompt:
                prompt = prompt.replace(segment, '')
        return prompt
# Path: discord_tron_client/classes/image_manipulation/diffusion.py
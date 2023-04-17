from compel import Compel
from torch import Generator
import torch

# Manipulating prompts for the pipeline.
class PromptManipulation:
    def __init__(self, pipeline, device):
        self.pipeline = pipeline
        self.compel = Compel(tokenizer=self.pipeline.tokenizer, text_encoder=pipeline.text_encoder, truncate_long_prompts=False)

    
    def process(self, prompt: str):
        conditioning = self.compel.build_conditioning_tensor(prompt)
        return conditioning
    
    def process_long_prompt(self, positive_prompt: str, negative_prompt: str):
        conditioning = self.compel.build_conditioning_tensor(positive_prompt)
        negative_conditioning = self.compel.build_conditioning_tensor(negative_prompt)
        [conditioning, negative_conditioning] = self.compel.pad_conditioning_tensors_to_same_length([conditioning, negative_conditioning])
        
        return conditioning, negative_conditioning

# Path: discord_tron_client/classes/image_manipulation/diffusion.py
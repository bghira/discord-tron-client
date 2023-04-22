from diffusers import StableDiffusionPipeline, StableDiffusionImageVariationPipeline, StableDiffusionImg2ImgPipeline, StableDiffusionSAGPipeline, StableDiffusionUpscalePipeline
from diffusers import DiffusionPipeline as Pipeline
from accelerate.utils import set_seed
from typing import Dict
from discord_tron_client.classes.hardware import HardwareInfo
from discord_tron_client.classes.app_config import AppConfig
import torch, gc, logging

hardware = HardwareInfo()
config = AppConfig()

class DiffusionPipelineManager:
    PIPELINE_CLASSES = {
        "img2img": StableDiffusionImg2ImgPipeline,
        "SAG": StableDiffusionSAGPipeline,
        "text2img": Pipeline,
        "prompt_variation": StableDiffusionImg2ImgPipeline,
        "variation": StableDiffusionImageVariationPipeline,
        "upscaler": StableDiffusionUpscalePipeline
    }
    def __init__(self):
        self.pipelines = {}
        hw_limits = hardware.get_hardware_limits()
        self.torch_dtype = torch.float16
        self.variation_attn_scaling = False
        self.use_attn_scaling = False
        self.model_id = None
        self.img2img = False
        self.SAG = False
        if hw_limits["gpu"] >= 16 and config.get_precision_bits() == 32:
            self.torch_dtype = torch.float32
        if hw_limits["gpu"] <= 16:
            logging.warn(f"Our GPU has less than 16GB of memory, so we will use attention scaling for image generation, resulting in much higher CPU use to lower VMEM use.")
            self.variation_attn_scaling = True
            self.use_attn_scaling = True
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.last_pipe_type = {}        # { "model_id": "text2img", ... }
        self.pipelines: Dict[str, Pipeline] = {}
        self.last_pipe_type: Dict[str, str] = {}

    def clear_pipeline(self, model_id: str) -> None:
        if model_id in self.pipelines:
            try:
                del self.pipelines[model_id]
                gc.collect()
                torch.clear_autocast_cache()
            except Exception as e:
                logging.error(f"Error when deleting pipe: {e}")

    def create_pipeline(self, model_id: str, pipe_type: str) -> Pipeline:
        pipeline_class = self.PIPELINE_CLASSES[pipe_type]
        if pipe_type in ["img2img"]:
            # Use the long prompt weighting pipeline.
            logging.debug(f"Creating a LPW pipeline for {model_id}")
            pipeline = pipeline_class.from_pretrained(model_id, torch_dtype=self.torch_dtype, custom_pipeline="lpw_stable_diffusion")
        else:
            logging.debug(f"Using standard pipeline for {model_id}")
            pipeline = pipeline_class.from_pretrained(model_id, torch_dtype=self.torch_dtype)
        if hasattr(pipeline, "safety_checker") and pipeline.safety_checker is not None:
            pipeline.safety_checker = lambda images, clip_input: (images, False)
        return pipeline

    def get_pipe(self, resolution: dict, model_id: str, img2img: bool = False, SAG: bool = False, prompt_variation: bool = False, variation: bool = False, upscaler: bool = False) -> Pipeline:
        gc.collect()
        logging.info("Generating a new pipe...")
        if self.use_attn_scaling:
            self.torch_dtype = torch.float16

        pipe_type = "img2img" if img2img else "SAG" if SAG else "prompt_variation" if prompt_variation else "variation" if variation else "upscaler" if upscaler else "text2img" 
        
        if model_id in self.last_pipe_type and self.last_pipe_type[model_id] != pipe_type:
            logging.warn(f"Clearing out an incorrect pipeline type for the same model. Going from {self.last_pipe_type[model_id]} to {pipe_type}. Model: {model_id}")
            self.clear_pipeline(model_id)

        if model_id not in self.pipelines:
            logging.debug(f"Creating pipeline type {pipe_type} for model {model_id}")
            self.pipelines[model_id] = self.create_pipeline(model_id, pipe_type)
            if pipe_type in ["prompt_variation", "variation"]:
                self.set_scheduler(self.pipelines[model_id])
                self.pipelines[model_id].enable_xformers_memory_efficient_attention(True)
                self.pipelines[model_id].set_use_memory_efficient_attention_xformers(True)
            if pipe_type in [ "upscaler", "text2img" ]:
                # Set the use of xformers library so that we can efficiently generate and upscale images.
                # @see https://huggingface.co/stabilityai/stable-diffusion-x4-upscaler/discussions/2
                self.set_scheduler(self.pipelines[model_id])
                self.pipelines[model_id].enable_xformers_memory_efficient_attention(True)
                self.pipelines[model_id].set_use_memory_efficient_attention_xformers(True)
        # This must happen here, or mem savings are minimal.
        self.pipelines[model_id].to(self.device)
        self.last_pipe_type[model_id] = pipe_type
        return self.pipelines[model_id]

    def get_variation_pipe(self, model_id):
        # Make way for the variation queen.
        logging.info("Clearing other poops.")
        self.delete_pipes(keep_model=model_id)
        logging.info("Generating a new img2img pipe...")
        self.pipelines[model_id] = StableDiffusionImageVariationPipeline.from_pretrained(
            pretrained_model_name_or_path=model_id, torch_dtype=self.torch_dtype, revision="v2.0"
        )
        self.set_scheduler(self.pipelines[model_id])
        from xformers.ops import MemoryEfficientAttentionFlashAttentionOp
        self.pipelines[model_id].enable_xformers_memory_efficient_attention(attention_op=MemoryEfficientAttentionFlashAttentionOp)
        self.pipelines[model_id].safety_checker = lambda images, clip_input: (images, False)
        self.pipelines[model_id].to(self.device)
        logging.info("Return the pipe...")
        return self.pipelines[model_id]
    
    def delete_pipes(self, keep_model: str = None):
        keys_to_delete = [pipeline for pipeline in self.pipelines if keep_model is None or pipeline != keep_model]

        for key in keys_to_delete:
            del self.pipelines[key]
            gc.collect()
        self.clear_cuda_cache()

    def clear_cuda_cache(self):
        if config.get_cuda_cache_clear_toggle():
            logging.info("Clearing the CUDA cache...")
            torch.cuda.empty_cache()
        else:
            logging.debug(f"NOT clearing CUDA cache. Config option `cuda_cache_clear` is not set, or is False.")
        
    def set_scheduler(self, pipe, user_config = None):
        if user_config is None or "scheduler" not in user_config or user_config["scheduler"] is None:
            logging.debug(f"Not setting user image gen scheduler. None is set.")
            return
        from diffusers import DPMSolverMultistepScheduler
        pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config, algorithm_type="dpmsolver++")

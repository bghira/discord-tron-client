from discord_tron_client.classes.image_manipulation.pipeline_runners.base_runner import BasePipelineRunner
from discord_tron_client.classes.image_manipulation.pipeline_runners.text2img import Text2ImgPipelineRunner
from discord_tron_client.classes.image_manipulation.pipeline_runners.img2img import Img2ImgPipelineRunner
from discord_tron_client.classes.image_manipulation.pipeline_runners.sdxl_base import SdxlBasePipelineRunner
from discord_tron_client.classes.image_manipulation.pipeline_runners.sdxl_refiner import SdxlRefinerPipelineRunner

runner_map = {
    "text2img": Text2ImgPipelineRunner,
    "img2img": Img2ImgPipelineRunner,
    "sdxl_base": SdxlBasePipelineRunner,
    "sdxl_refiner": SdxlRefinerPipelineRunner,
}
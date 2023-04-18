import logging
from discord_tron_client.classes.app_config import AppConfig
config = AppConfig()

class ResolutionManager:
    resolutions = [
        # 1:1 aspect ratio
        {"width": 128, "height": 128, "scaling_factor": 100},
        {"width": 256, "height": 256, "scaling_factor": 88},
        {"width": 512, "height": 512, "scaling_factor": 30},
        {"width": 1024, "height": 1024, "scaling_factor": 30},
        {"width": 2048, "height": 2048, "scaling_factor": 30},
        {"width": 4096, "height": 4096, "scaling_factor": 30},

        # 2:3 aspect ratio
        {"width": 128, "height": 192, "scaling_factor": 80},
        {"width": 256, "height": 384, "scaling_factor": 60},
        {"width": 512, "height": 768, "scaling_factor": 49},
        {"width": 1024, "height": 1536, "scaling_factor": 30},
        {"width": 2048, "height": 3072, "scaling_factor": 30},
        {"width": 4096, "height": 6144, "scaling_factor": 30},

        # 3:2 aspect ratio
        {"width": 192, "height": 128, "scaling_factor": 94},
        {"width": 384, "height": 256, "scaling_factor": 76},
        {"width": 768, "height": 512, "scaling_factor": 52},
        {"width": 1536, "height": 1024, "scaling_factor": 30},
        {"width": 3072, "height": 2048, "scaling_factor": 30},
        {"width": 6144, "height": 4096, "scaling_factor": 30},

        # 16:9 aspect ratio
        {"width": 256, "height": 144, "scaling_factor": 40},
        {"width": 512, "height": 288, "scaling_factor": 40},
        {"width": 1024, "height": 576, "scaling_factor": 40},
        {"width": 1280, "height": 720, "scaling_factor": 30},
        {"width": 1920, "height": 1080, "scaling_factor": 30},
        {"width": 2160, "height": 1440, "scaling_factor": 30},
        {"width": 3840, "height": 2160, "scaling_factor": 30},
        {"width": 7680, "height": 4320, "scaling_factor": 30},
    ]
    @staticmethod
    def get_scaling_factor(width, height, scaled_resolutions):
        for res in scaled_resolutions:
            if res["width"] == width and res["height"] == height:
                return int(res["scaling_factor"])
        return None

    @staticmethod
    def is_valid_resolution(width, height):
        for res in ResolutionManager.resolutions:
            if res["width"] == width and res["height"] == height:
                return True
        total_pixel_area = width * height
        aspect_ratio = ResolutionManager.aspect_ratio({"width": width, "height": height})
        max_resolution = config.get_max_resolution_by_aspect_ratio(aspect_ratio)
        max_pixel_area = max_resolution["width"] * max_resolution["height"]
        if total_pixel_area > max_pixel_area:
            return False
        return True
    @staticmethod
    def validate_sag_resolution(model_config, user_config, width, height):
        correct_resolution = {"width": width, "height": height}
        if model_config["sag_capable"] is None or model_config["sag_capable"] is False:
            correct_resolution = ResolutionManager.get_highest_resolution('1:1', config.get_max_resolution_by_aspect_ratio('1:1'))
        return (correct_resolution["width"], correct_resolution["height"])

    @staticmethod
    def aspect_ratio(resolution_item: dict):
        from math import gcd
        width = resolution_item["width"]
        height = resolution_item["height"]
        # Calculate the greatest common divisor of width and height
        divisor = gcd(width, height)

        # Calculate the aspect ratio
        ratio_width = width // divisor
        ratio_height = height // divisor

        # Return the aspect ratio as a string in the format "width:height"
        return f"{ratio_width}:{ratio_height}"

    # Generation resolutions have to be more carefully selected than resize resolutions.
    @staticmethod
    def nearest_generation_resolution(side_x: int, side_y: int):
        aspect_ratio = ResolutionManager.aspect_ratio({"width": side_x, "height": side_y})
        max_resolution_config = config.get_max_resolution_by_aspect_ratio(aspect_ratio)
        logging.info(f"Our max resolution config, {max_resolution_config}")
        max_resolution = ResolutionManager.get_highest_resolution(aspect_ratio, max_resolution_config)
        if int(side_x) * int(side_y) <= int(max_resolution["width"]) * int(max_resolution["height"]):
            # Total pixel area is under our maximum.
            return side_x, side_y
        else:
            logging.info(f"Nearest resolution for {side_x}x{side_y} is larger than max resolution {max_resolution} and no better alternative could be found.")
            return max_resolution["width"], max_resolution["height"]

    @staticmethod
    def nearest_scaled_resolution(resolution: dict, user_config: dict):
        # We will scale by default, to 4x the requested resolution. Big energy!
        factor = user_config.get("resize", 1)
        if factor == 1 or factor == 0:
            # Do not bother rescaling if it's set to 1 or 0
            return resolution
        aspect_ratio = ResolutionManager.aspect_ratio(resolution)
        max_resolution_config = config.get_max_resolution_by_aspect_ratio(aspect_ratio)

        logging.info(f"Resize configuration is set by user factoring at {factor} based on our max resolution config, {max_resolution_config}.")

        width = resolution["width"]
        height = resolution["height"]

        new_width = int(width * factor)
        new_height = int(height * factor)
        new_aspect_ratio = ResolutionManager.aspect_ratio({"width": new_width, "height": new_height})

        max_resolution = ResolutionManager.get_highest_resolution(aspect_ratio, max_resolution_config)

        if ResolutionManager.is_valid_resolution(new_width, new_height):
            if int(new_width) * int(new_height) <= int(max_resolution["width"]) * int(max_resolution["height"]):
                logging.info(f"Nearest resolution for AR {aspect_ratio} is {new_width}x{new_height}.")
                return {"width": new_width, "height": new_height}
        # Loop through each of ResolutionManager.resolutions by aspect ratio to determine the first resolution that's >= the new resolution
        for res in ResolutionManager.resolutions:
            if ResolutionManager.aspect_ratio(res) == aspect_ratio and res["width"] >= new_width:
                logging.info(f"Nearest resolution for AR {aspect_ratio} is {res}.")
                return res
                
        logging.info(f"Nearest resolution for AR {aspect_ratio} is larger than max resolution {max_resolution} and no better alternative could be found.")
        return max_resolution
    @staticmethod
    def get_highest_resolution(aspect_ratio: str, max_resolution_config: dict):
        # Calculate the aspect ratio of the input image
        # Filter the resolutions list to only include resolutions with the same aspect ratio as the input image
        filtered_resolutions = [r for r in ResolutionManager.resolutions if ResolutionManager.aspect_ratio(r) == aspect_ratio]

        # Check for a maximum resolution cap in the configuration
        max_res_cap = max_resolution_config.get(aspect_ratio)

        # If there's a cap, filter the sorted resolutions list to only include resolutions below the cap
        if max_res_cap:
            filtered_resolutions = [r for r in filtered_resolutions if r["width"] <= max_res_cap["width"] and r["height"] <= max_res_cap["height"]]

        # Return the last (highest) resolution from the sorted list, or None if the list is empty
        return filtered_resolutions[-1] if filtered_resolutions else None

    @staticmethod
    def get_aspect_ratio_and_sides(config, resolution):
        # Current request's aspect ratio
        aspect_ratio = ResolutionManager.aspect_ratio(resolution)
        # Get the maximum resolution for the current aspect ratio
        side_x = config.get_max_resolution_width(aspect_ratio)
        side_y = config.get_max_resolution_height(aspect_ratio)
        logging.info('Aspect ratio ' + str(aspect_ratio) + ' has a maximum resolution of ' + str(side_x) + 'x' + str(side_y) + '.')
        if resolution["width"] <= side_x and resolution["height"] <= side_y:
            side_x = resolution["width"]
            side_y = resolution["height"]
        return aspect_ratio, side_x, side_y
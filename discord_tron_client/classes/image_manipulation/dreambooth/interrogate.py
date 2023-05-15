import os, logging, xformers, accelerate
from PIL import Image
from clip_interrogator import Config, Interrogator, LabelTable, load_list

# Directory where the images are located
image_dir = 'images'



def interrogator(clip_model_name = "ViT-H-14/laion2b_s32b_b79k"):
    # Create an Interrogator instance with the latest CLIP model for Stable Diffusion 2.1
    ci = Interrogator(Config(clip_model_name=clip_model_name))
    return ci

def load_terms(filename, interrogator):
    # Load your list of terms
    table = LabelTable(load_list('terms.txt'), 'terms', interrogator)
    logging.debug(f'Loaded {len(table)} terms from {filename}')
    return table

active_interrogator = None
def process_directory(image_dir = 'images', terms_file = None):
    # Go through all the images in the directory
    global active_interrogator
    if active_interrogator is None:
        active_interrogator = interrogator()
    if terms_file is not None:
        table = load_terms(terms_file, active_interrogator)

    for filename in os.listdir(image_dir):
        if filename.endswith(".jpg") or filename.endswith(".png"):
            # Open and convert the image
            image = Image.open(os.path.join(image_dir, filename)).convert('RGB')
            if terms_file is not None:
                # Get the best match for the image
                best_match = table.rank(active_interrogator.image_to_features(image), top_count=1)[0]
            else:
                best_match = active_interrogator.generate_caption(image)

            # Print the result
            print(f'Best match for {filename}: {best_match}')
            # Write the best match to {filename}.txt:
            with open(os.path.join(image_dir, f'{filename}.txt'), 'w') as f:
                f.write(best_match)
            

if __name__ == "__main__":
    process_directory('/home/kash/Downloads/datasets/diana')
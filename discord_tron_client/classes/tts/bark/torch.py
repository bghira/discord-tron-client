from discord_tron_client.classes.app_config import AppConfig
from bark.api import generate_audio
from bark.generation import preload_models
from bark.generation import SAMPLE_RATE
import os, sys, json, logging, time, io, re
from pydub import AudioSegment
from scipy.io.wavfile import write as write_wav
from typing import List
import numpy as np

config = AppConfig()
sample_text_prompt = """
     Hello, my name is Suno. And, uh — and I like pizza. [laughs] 
     But I also have other interests such as playing tic tac toe.
"""


class BarkTorch:
    def __init__(self):
        self.loaded = False
        self.model = "Bark"
        self.usage = None

    def details(self):
        return f"PyTorch running the {self.model} audio generation model"

    def get_usage(self):
        return self.usage or None

    def load_model(self):
        if self.loaded:
            logging.debug(f"Not reloading Bark TTS models.")
            return
        logging.info(f"Loading Bark TTS model, as it was not already found loaded.")
        preload_models()
        self.loaded = True

    def _generate(self, prompt, user_config, character_voice: str = None):
        # generate audio from text
        if (
            character_voice is None
            or character_voice == "none"
            or character_voice == "default"
        ):
            character_voice = None
        logging.debug(f"Generating text {prompt[32:]}.. with voice {character_voice}")
        audio = generate_audio(prompt, history_prompt=character_voice)
        return audio, None

    def generate(self, prompt, user_config):
        logging.debug(f"Begin Bark generate() routine")
        time_begin = time.time()
        # User settings overrides.
        audio, _, semantic_x = self.generate_long(
            prompt=prompt, user_config=user_config
        )
        time_end = time.time()
        time_duration = time_end - time_begin
        logging.debug(f"Completed generation in {time_duration} seconds: {audio}")
        if audio is None:
            raise RuntimeError(f"{self.model} returned no result.")
        self.usage = {"time_duration": time_duration}

        return audio, SAMPLE_RATE, semantic_x

    def split_text_prompt(self, text_prompt, maxword=30):
        text_prompt = re.sub(r"\s{2,}", " ", text_prompt)
        segments = re.split(r"(?<=[,.])\s*", text_prompt)
        segments = [re.sub(r"[^a-zA-Z0-9,. ]", "", segment) for segment in segments]

        result = []
        buffer = ""
        for segment in segments:
            words = segment.split()

            if len(buffer.split()) + len(words) > maxword:
                while len(words) > maxword:
                    result.append(" ".join(words[:maxword]) + ".")
                    words = words[maxword:]
            if len(buffer.split()) + len(words) < 15:
                buffer += " " + segment
            else:
                result.append(buffer.strip() + segment)
                buffer = ""

        if buffer:
            result.append(buffer.strip())

        result = [
            segment.rstrip(",") + "." if not segment.endswith(".") else segment
            for segment in result
        ]

        return result, len(result)

    def estimate_spoken_time(self, text, wpm=150, time_limit=14):
        # Remove text within square brackets
        text_without_brackets = re.sub(r"\[.*?\]", "", text)

        words = text_without_brackets.split()
        word_count = len(words)
        time_in_seconds = (word_count / wpm) * 60

        if time_in_seconds > time_limit:
            return True, time_in_seconds
        else:
            return False, time_in_seconds

    def generate_long(self, prompt, user_config):
        # Split the prompt into smaller segments
        segments = prompt.split("\n")
        return self.generate_long_from_segments(segments, user_config)

    def generate_long_from_segments(self, prompts: List[str], user_config):
        # Generate audio for each prompt
        audio_segments = []
        actors = user_config.get("tts_actors", None)
        logging.debug(
            f"Generating long prompt with {len(prompts)} segments. using actors {actors}"
        )
        current_voice = None
        for prompt in prompts:
            line, voice = BarkTorch.process_line(prompt, actors)
            if voice is not None:
                # Set a voice, if found. Otherwise, keep last voice.
                current_voice = voice
            audio, semantics = self._generate(line, user_config, current_voice)
            audio_segments.append(audio)
        # Concatenate the audio segments
        concatenated_audio = self.concatenate_audio_segments(audio_segments)
        return concatenated_audio, SAMPLE_RATE, semantics

    @staticmethod
    def clean_audio(audio):
        pass

    @staticmethod
    def concatenate_audio_segments(audio_segments):
        combined_audio = np.array([], dtype=np.int16)

        for audio in audio_segments:
            # Concatenate the audio
            combined_audio = np.concatenate((combined_audio, audio))

        return combined_audio

    @staticmethod
    def process_line(line, characters):
        if characters is None:
            logging.debug(
                f"No characters were given to process_line so we will just return the input line: {line}"
            )
            return line, None
        logging.debug(f"We have the characters we need.")
        pattern = r"\{([^}]+)\}:?"
        match = re.search(pattern, line)
        logging.debug(f"For line {line} we have {match} match?")
        if match:
            actor = match.group(1)
            logging.debug(f"We found actor {actor}")
            line = re.sub(pattern, "", line).strip()
            logging.debug(f"Stripping the actor out of the line to: {line}")
            # This can strip out "not-found" {STRINGS} so beware...
            character_voice = characters.get(actor, {}).get("voice", None)
            logging.debug(f"Selected character voice: {character_voice}")
        else:
            character_voice = None
        return line, character_voice

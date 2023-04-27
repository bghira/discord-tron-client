from discord_tron_client.classes.app_config import AppConfig
import discord_tron_client.classes.stableml.helpers.predict as predict

import os, sys, json, logging, time

config = AppConfig()

class StableMLPy:
    def __init__(self):
        self.model = config.stableml_model_default()
        self.model_config = None
        self.tokenizer = None
        self.stableml = None

    def load_model(self):
        self.tokenizer, self.stableml = predict.load(self.model)

    def details(self):
        return f'StableML.Py running the {self.model} parameter model'

    def get_usage(self):
        return self.usage or None

    def _predict(self, prompt, seed = 1337, max_tokens = 512, temperature = 0.8, repeat_penalty = 1.1, top_p = 0.95, top_k=40):
        try:
            self.llama.params.seed = seed
        except Exception as e:
            logging.error(f"Could not set LLaMA prompt seed. Perhaps the ABI changed? {e}")
        """
            >>> print(f"Result: {result}")
                Result: {'id': 'cmpl-4b2d3c01-3e7d-41aa-8c2c-9a87ca4ad35d', 'object': 'text_completion', 'created': 1682215736,
                'model': '/archive/models/LLaMA/7B/ggml-model-f16.bin',
                'choices': [{'text': '\nI’m not really sure what to think about this yet, so I’ll leave it at that for now.', 'index': 0, 'logprobs': None, 'finish_reason': 'stop'}],
                'usage': {'prompt_tokens': 10, 'completion_tokens': 25, 'total_tokens': 35}}
        """
        return self.llama(prompt=prompt, max_tokens=max_tokens, temperature=temperature, top_p=top_p, top_k=top_k, repeat_penalty=repeat_penalty)
    
    def predict(self, prompt, user_config, max_tokens = 4096, temperature = 1.0, repeat_penalty = 1.1, top_p = 0.95, top_k=40):
        logging.debug(f"Begin StableMLPy prediction routine")

        logging.debug(f"Our received parameters: max_tokens {max_tokens} top_p {top_p} top_k {top_k} repeat_penalty {repeat_penalty} temperature {temperature}")
        time_begin = time.time()
        # User settings overrides.
        seed = user_config.get("seed", None)
        temperature = user_config.get("temperature", temperature)
        top_p = user_config.get("top_p", top_p)
        top_k = user_config.get("top_k", top_k)
        repeat_penalty = user_config.get("repeat_penalty", repeat_penalty)
        # Maybe the user wants fewer tokens.
        user_max_tokens = user_config.get("max_tokens", max_tokens)
        if max_tokens >= user_max_tokens:
            max_tokens = user_max_tokens
        logging.debug(f"Our post-override parameters: max_tokens {max_tokens} top_p {top_p} top_k {top_k} repeat_penalty {repeat_penalty} temperature {temperature}")

        # If the user has not specified a seed, we will use the current time.
        if seed is None or seed == 0:
            logging.debug("Timestamp being used as the seed.")
            seed = int(time_begin)
        elif seed == -1:
            # -1 is a special condition for randomizing the seed more than just using the timestamp.
            logging.debug("Ultra-seed randomizer engaged!")
            import random
            seed = random.randint(0, 999999999)
        else:
            logging.debug("A pre-selected seed was provided.")
        logging.debug(f"Seed chosen: {seed}")

        logging.debug("Beginning Llama.cpp prediction..")
        cpp_result = self._predict(prompt=prompt, seed=seed, max_tokens=max_tokens, temperature=temperature, repeat_penalty=repeat_penalty, top_p=top_p, top_k=top_k)
        time_end = time.time()
        time_duration = time_end - time_begin
        logging.debug(f"Completed prediction in {time_duration} seconds: {cpp_result}")
        if cpp_result is None:
            raise RuntimeError("LLaMA.cpp returned no result.")
        if "choices" not in cpp_result:
            raise RuntimeError("LLaMA.cpp returned an invalid result.")
        if "text" not in cpp_result["choices"][0] or cpp_result["choices"][0]["text"] == "":
            raise RuntimeError("LLaMA.cpp returned an empty set.")
        if "finish_reason" not in cpp_result["choices"][0]:
            logging.warn(f"LLaMA.cpp did not return a finish_reason: {cpp_result}")
        self.usage = {"time_duration": time_duration}
        if "usage" in cpp_result:
            self.usage.update(cpp_result["usage"])
        return cpp_result["choices"][0]['text']
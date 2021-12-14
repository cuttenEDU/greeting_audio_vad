import yaml


class Config():
    CONFIG_KEYS = ["window_duration", "sample_rate", "n_fft", "win_length", "hop_length", "n_mels", "certainty_thresh",
                   "certainty_detects", "certainty_window", "vad_release", "model_path"]

    def __init__(self, path="config.yml"):
        self.path = path
        try:
            with open(path, "r") as file:
                config = yaml.load(file, Loader=yaml.FullLoader)
        except OSError as e:
            raise RuntimeError(f"Can't open config file in provided path: {path}")

        for k in self.CONFIG_KEYS:
            setattr(self, k, config[k])

    def __repr__(self):
        config_str = ""
        for k, v in self.__dict__.items():
            config_str += f"{k}:\t{v}\n"
        return config_str[:-1]

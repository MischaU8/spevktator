import os

from dostoevsky.data import AVAILABLE_FILES, DATA_BASE_PATH, DataDownloader
from dostoevsky.tokenization import RegexTokenizer
from dostoevsky.models import FastTextSocialNetworkModel
import fasttext

# disable warning
# Warning : `load_model` does not return WordVectorModel or SupervisedModel any more,
# but a `FastText` object which is very similar.
fasttext.FastText.eprint = lambda x: None

tokenizer = RegexTokenizer()
try:
    model = FastTextSocialNetworkModel(tokenizer=tokenizer)
except ValueError:
    model = None


def download(model_filename="fasttext-social-network-model"):
    downloader = DataDownloader()
    if model_filename not in AVAILABLE_FILES:
        raise ValueError(f"Unknown package: {model_filename}")
    source, destination = AVAILABLE_FILES[model_filename]
    destination_path: str = os.path.join(DATA_BASE_PATH, destination)
    if os.path.exists(destination_path):
        # print(f"Model {model_filename} already exists on {destination_path}")
        return
    downloader.download(source=source, destination=destination)


def predict(text, k=-1):
    if model is None:
        raise ValueError("Model not installed")
    result = model.predict(text, k)
    return result

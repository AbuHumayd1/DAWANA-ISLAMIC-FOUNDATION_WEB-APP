from .base import *


DEBUG = True
DIC_MEMORY_STORAGE = env("DIC_MEMORY_STORAGE", default="local")
ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS",
    default=["127.0.0.1", "localhost"],
)

"""compile-gfx -- decoders for Compile's graphics formats.

Extraction only. Each patch project keeps its own reinsertion layer (exact
byte budgets, archive rebuilds, disk-image injection, pointer tables); what
lives here is the codec and container knowledge those projects would
otherwise each copy -- and drift on. Two real bugs came from exactly that
drift, so the encoders live here beside their decoders too.

    from compilegfx import load, to_png
    to_png(load(open("MAIN14.GCN", "rb").read()), "out.png")
"""
from .detect import NotAnImage, load
from .image import Bitmap, to_png

__all__ = ["Bitmap", "NotAnImage", "load", "to_png"]
__version__ = "0.1.0"

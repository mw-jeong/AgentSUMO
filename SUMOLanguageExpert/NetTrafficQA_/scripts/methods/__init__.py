from .raw import ask as ask_raw
from .adj import ask as ask_adj
from .codegen import ask as ask_codegen

METHODS = {
    "raw": ask_raw,
    "adj": ask_adj,
    "codegen": ask_codegen,
}

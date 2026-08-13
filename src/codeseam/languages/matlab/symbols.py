BUILTIN_FUNCTIONS = frozenset(
    {
        "abs", "angle", "conv", "corrcoef", "detrend", "disp", "eig", "eps",
        "fft", "fftshift", "filter", "find", "floor", "fprintf", "ifft", "length",
        "linspace", "max", "mean", "median", "min", "mod", "numel", "ones",
        "plot", "rand", "randi", "randn", "reshape", "save", "size", "sort",
        "sqrt", "std", "sum", "zeros",
    }
)

# Frontend-only syntax/standard-library knowledge.  The language-neutral core sees
# only CallAbstraction values and never imports this MATLAB-specific list.
PRIMITIVE_FUNCTIONS = frozenset(
    {
        "abs", "angle", "double", "eps", "find", "floor", "length", "linspace",
        "max", "mean", "median", "min", "mod", "norm", "numel", "ones", "rand",
        "randi", "randn", "reshape", "size", "sort", "sqrt", "squeeze", "std",
        "sum", "zeros", "disp", "fprintf", "plot", "save",
    }
)

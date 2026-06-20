# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""Contract gate: public docstrings/comments must not reference imperal_kernel.* module paths.

D3 gate — part of the L0 engine-neutral seal. Module-path references like
`imperal_kernel.x.y` tie the public API surface to an internal substrate
implementation detail. After the 5.5.0 docstring scrub, three modules had
remaining references missed by the initial pass; this test enforces they stay
clean going forward.
"""
import inspect

import imperal_sdk.chat.error_codes as ec
import imperal_sdk.chat.narration as nr
import imperal_sdk.runtime.llm_provider as lp


def test_no_imperal_kernel_module_refs_in_public_docstrings():
    """No imperal_kernel.* module-path reference may appear in these modules' source."""
    for mod in (ec, nr, lp):
        src = inspect.getsource(mod)
        # module-path references like `imperal_kernel.x.y` must be gone from docstrings/comments
        assert "imperal_kernel." not in src, (
            f"{mod.__name__} still references imperal_kernel.* "
            "(substrate-neutral wording required in public-facing source)"
        )

"""PR 2: Fundamentals' price and dollar-volume floors and its type filter are settings (defaults unchanged)."""
from __future__ import annotations

from revenuechaser.core import board_settings
from revenuechaser.module_fundamentals import config, freeze
from revenuechaser.module_fundamentals import settings as fsettings


def test_effective_reads_the_config_defaults_with_no_override(rawstore_tmp_db):
    e = fsettings.effective()
    assert (e.min_price, e.min_dollar_volume, e.operating_only) == (config.MIN_PRICE, config.MIN_DOLLAR_VOLUME, True)
    assert e.prefilter_cfg().MIN_PRICE == config.MIN_PRICE
    assert e.override_values == ()



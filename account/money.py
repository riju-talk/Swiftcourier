"""Single place that decides how rupee amounts are represented and rounded.

Wallet money is stored as ``DecimalField(max_digits=12, decimal_places=2)``. The
rest of the codebase still passes ``float``/``int``/``str`` around, so every value
that crosses into the wallet layer (``User.credit``/``debit``/``have_balance``,
``Transaction.create_transaction`` and friends) is funnelled through
``to_money()`` first. That keeps ``Decimal + float`` ``TypeError``s out of the
money paths and guarantees a consistent 2-dp, half-up rounding rule.
"""

from decimal import Decimal, ROUND_HALF_UP

CENTS = Decimal("0.01")
ZERO = Decimal("0.00")


def to_money(value) -> Decimal:
    """Coerce ``value`` to a 2-dp :class:`~decimal.Decimal` (banker-free, half-up).

    Accepts ``Decimal``, ``int``, ``float`` or numeric ``str``. ``None`` becomes
    ``0.00``. ``float`` goes through ``str()`` so we quantize the *printed*
    value (57604.5 -> 57604.50) rather than the binary artefact.
    """
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        d = value
    elif isinstance(value, float):
        d = Decimal(str(value))
    else:
        d = Decimal(value)
    return d.quantize(CENTS, rounding=ROUND_HALF_UP)

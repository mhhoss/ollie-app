from __future__ import annotations

from ollie.bot import copy_fa, keyboards
from ollie.domain.models import Product, ProductKind, Variant


def test_cb_and_parse_cb_roundtrip() -> None:
    data = keyboards.cb("approve", "A7K2M9", "receipt_submitted")
    assert data == "approve:A7K2M9:receipt_submitted"
    assert keyboards.parse_cb(data) == ("approve", "A7K2M9", "receipt_submitted")


def test_cb_defaults_entity_and_state() -> None:
    data = keyboards.cb("nav")
    assert keyboards.parse_cb(data) == ("nav", "_", "_")


def test_root_reply_keyboard_has_three_labels() -> None:
    markup = keyboards.root_reply_keyboard()
    labels = {btn.text for row in markup.keyboard for btn in row}
    assert labels == {copy_fa.BTN_PRODUCTS, copy_fa.BTN_MY_ORDERS, copy_fa.BTN_SUPPORT}


def test_categories_keyboard_includes_back_button() -> None:
    markup = keyboards.categories_keyboard([(1, "اشتراک‌ها"), (2, "شارژ حساب")])
    last_row = markup.inline_keyboard[-1]
    assert last_row[0].text == copy_fa.BTN_BACK
    assert keyboards.parse_cb(last_row[0].callback_data or "")[0] == "nav"


def test_product_detail_keyboard_with_variants_only_lists_in_stock_ones() -> None:
    product = Product(
        id=1,
        kind=ProductKind.DIGITAL,
        name="p",
        description="",
        price=1000,
        cost_price=500,
        is_active=True,
    )
    variants = [
        Variant(id=1, product_id=1, label="v1", price_delta=0, stock=2, reserved=0),
        Variant(id=2, product_id=1, label="v2", price_delta=0, stock=1, reserved=1),  # sold out
    ]
    markup = keyboards.product_detail_keyboard(product, variants, cart_count=0)
    labels = [btn.text for row in markup.inline_keyboard for btn in row]
    assert "v1" in labels
    assert "v2" not in labels


def test_product_detail_keyboard_shows_cart_badge_only_when_nonempty() -> None:
    product = Product(
        id=1,
        kind=ProductKind.DIGITAL,
        name="p",
        description="",
        price=1000,
        cost_price=500,
        is_active=True,
    )
    empty_cart = keyboards.product_detail_keyboard(product, [], cart_count=0)
    with_cart = keyboards.product_detail_keyboard(product, [], cart_count=2)

    empty_labels = [btn.text for row in empty_cart.inline_keyboard for btn in row]
    cart_labels = [btn.text for row in with_cart.inline_keyboard for btn in row]

    assert not any("🛒" in label for label in empty_labels)
    assert copy_fa.BTN_CART.format(count=2) in cart_labels


def test_owner_reject_reasons_keyboard_has_one_button_per_reason_plus_custom_and_cancel() -> None:
    markup = keyboards.owner_reject_reasons_keyboard("A7K2M9", "receipt_submitted")
    buttons = [btn for row in markup.inline_keyboard for btn in row]
    non_custom_reasons = [r for r in copy_fa.REJECT_REASONS if r[0] != "custom"]
    # one row per fixed reason, plus one row with [custom, cancel]
    assert len(buttons) == len(non_custom_reasons) + 2
    actions = {keyboards.parse_cb(btn.callback_data or "")[0] for btn in buttons}
    assert "reason_custom" in actions
    assert "reason_cancel" in actions


def test_owner_new_receipt_keyboard_carries_expected_state_for_e2_guard() -> None:
    markup = keyboards.owner_new_receipt_keyboard("A7K2M9", "receipt_submitted")
    approve_button = markup.inline_keyboard[0][0]
    action, entity_id, expected_state = keyboards.parse_cb(approve_button.callback_data or "")
    assert action == "approve"
    assert entity_id == "A7K2M9"
    assert expected_state == "receipt_submitted"

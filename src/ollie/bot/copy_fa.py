"""
Every Persian string the bot can show a human, in one file.

Rules:
1. No Persian literal exists anywhere else under `src/ollie/bot/` — the
   layer that actually assembles messages and sends them. Enforced by
   `tests/bot/test_copy_isolation.py`. (`ollie.domain` and `ollie.fmt`
   are out of scope for that scan on purpose — see its module
   docstring for why.)
2. Constants are named for their spec screen (`docs/m1-spec.html`):
   `C9_INVOICE`, `O1_NEW_RECEIPT`, `E1_USE_BUTTONS`. The spec is the
   source of truth for the text; where it describes behavior but gives
   no literal string (E8), the constant here is flagged as authored,
   not transcribed, and needs the same native-speaker read as
   everything else before ship.
3. Templates use `str.format` with named fields only — never
   positional, never f-strings — so a caller can't silently reorder
   them. A handful of templates are assembled here from smaller
   fragments (`ORDER_CODE_LINE`, `DIVIDER`, ...) via plain string
   concatenation at *module load time*; that's not caller-facing
   interpolation, it's just avoiding repeating the same fragment eight
   times, and every fragment used that way is itself a plain literal.
4. No number or date formatting happens here. Every value a template
   expects — amounts, dates, counts, quantities — is a string the
   caller has already rendered with `ollie.fmt` (Persian digits,
   grouping, Jalali) before calling `.format()`. This module never
   imports `ollie.fmt` for that reason: if it needed to, that would be
   a sign a template was doing a caller's job.

One deliberate, spec-diverging choice, made explicit here rather than
silently: wherever the spec's mockup shows a *static illustrative
example* containing ASCII digits inside otherwise-Persian bot copy
(C7's phone-format hint), the literal here uses Persian digits instead
— consistent with the spec's own global convention ("Persian digits
... render-time"), and required by this module's own format-safety
test (no ASCII digit outside a `{placeholder}`). Every other ASCII-
looking digit in the spec's mockups (an example order code, an example
tracking number) is *dynamic data* a real message would never hold as
a literal — those became `{placeholder}` fields instead.

`STATUS_LABELS` covers all eight `OrderState` values, not just the six
the spec's C15 section lists by name — `draft` never appears in a
persisted order so it borrows `awaiting_receipt`'s label defensively,
and `rejected` (a live, non-terminal state a customer's order history
can genuinely sit in) gets a label in the same voice as the other five
since the spec doesn't supply one.
"""

from __future__ import annotations

from ollie.domain.states import OrderState

# ── 1. Fragments ──────────────────────────────────────────────────────
ORDER_CODE_LINE = "کد سفارش: <code>{order_code}</code>"
DATE_LINE = "تاریخ: {date}"
DIVIDER = "──────────────"

# ── 2. BTN ────────────────────────────────────────────────────────────
BTN_PRODUCTS = "🛍 محصولات"
BTN_MY_ORDERS = "📦 سفارش‌های من"
BTN_SUPPORT = "☎️ پشتیبانی"
BTN_BACK = "🔙 بازگشت"
BTN_BACK_TO_CART = "🔙 بازگشت به سبد"
BTN_BACK_TO_INVOICE = "🔙 بازگشت به فاکتور"
BTN_CANCEL = "🔙 انصراف"

BTN_PRODUCT_LABEL = "{product_name} — {price}"
BTN_PRODUCT_LABEL_OUT_OF_STOCK = "⛔️ {product_name} — {price}"
BTN_ADD_TO_CART = "➕ افزودن به سبد خرید"
BTN_CART = "🛒 سبد خرید ({count})"

BTN_CHECKOUT = "✅ ثبت سفارش"
BTN_EDIT_CART = "✏️ ویرایش"
BTN_CONTINUE_SHOPPING = "🛍 ادامه خرید"
BTN_DONE_EDITING = "✅ تمام"
BTN_DECREMENT = "➖"
BTN_INCREMENT = "➕"
BTN_REMOVE_ITEM = "🗑"

BTN_USE_SAVED_PROFILE = "✅ همین اطلاعات"
BTN_CHANGE_PROFILE = "✏️ تغییر"
BTN_SEND_MY_CONTACT = "📱 ارسال شماره من"

BTN_SEND_RECEIPT = "📤 ارسال فیش واریزی"
BTN_CANCEL_ORDER = "❌ انصراف از سفارش"
BTN_RESEND_RECEIPT = "📤 ارسال مجدد فیش"
BTN_VIEW_INVOICE = "🧾 مشاهده فاکتور"

BTN_APPROVE = "✅ تأیید"
BTN_REJECT = "❌ رد"
BTN_MSG_CUSTOMER = "💬 پیام به مشتری"
BTN_VIEW_CUSTOMER = "👤 مشتری"

BTN_REASON_AMOUNT_MISMATCH = "💰 مبلغ مطابقت ندارد"
BTN_REASON_UNREADABLE = "🔍 فیش خوانا نیست"
BTN_REASON_DUPLICATE = "♻️ فیش تکراری است"
BTN_REASON_NOT_RECORDED = "🚫 واریزی ثبت نشده"
BTN_CUSTOM_REASON = "✏️ دلیل دلخواه"

BTN_ADD_STOCK = "➕ افزودن موجودی"
BTN_MANUAL_SEND = "💬 ارسال دستی"
BTN_ENTER_TRACKING = "📮 ثبت کد رهگیری"
BTN_PENDING_ORDERS = "⏳ سفارش‌های در انتظار ({count})"
BTN_ALL_ORDERS = "📦 همه سفارش‌ها"
BTN_CREDENTIAL_POOL = "🔑 موجودی تحویل"
BTN_ADD_CREDENTIALS = "➕ افزودن"
BTN_SUPPORT_MESSAGES = "💬 پیام‌های پشتیبانی"
BTN_BACKUP = "💾 پشتیبان‌گیری"
BTN_REPLY = "↩️ پاسخ"

# ── 3. Customer screens C1–C15 ─────────────────────────────────────────
C1_WELCOME = (
    "سلام 👋\nبه فروشگاه <b>{store_name}</b> خوش آمدید.\n\n"
    "برای ثبت سفارش، یکی از گزینه‌های زیر را انتخاب کنید."
)

C2_CHOOSE_CATEGORY = "دسته‌بندی مورد نظر خود را انتخاب کنید:"
C2_EMPTY_CATALOG = "در حال حاضر محصولی برای فروش موجود نیست."

C3_PRODUCT_LIST_HEADER = "محصولات دسته <b>{category_name}</b>:"

C4_AVAILABLE = "✅ موجود"
C4_OUT_OF_STOCK = "⛔️ ناموجود"
C4_PRODUCT_DETAIL = (
    "<b>{product_name}</b>\n\n{description}\n\n💰 قیمت: {price}\n{availability_line}"
)

C5_CART_HEADER = "🛒 <b>سبد خرید شما</b>"
C5_CART_LINE = "{index}. {product_name} × {quantity} — {line_total}"
C5_CART_TOTAL = "جمع کل: <b>{total}</b>"
C5_EMPTY_CART = "سبد خرید شما خالی است."

C6_ASK_NAME = "لطفاً نام و نام خانوادگی خود را وارد کنید:"
C6_SAVED_PROFILE_PROMPT = "اطلاعات قبلی شما: {full_name} — {phone}"
C6_ERROR_INVALID_NAME = "نام وارد شده کامل نیست. لطفاً نام و نام خانوادگی را با فاصله بنویسید."

C7_ASK_PHONE = "شماره تماس خود را وارد کنید یا با دکمه زیر ارسال کنید.\n\n<code>۰۹۱۲۱۲۳۴۵۶۷</code>"
C7_ERROR_INVALID_PHONE = (
    "شماره وارد شده معتبر نیست. یک شماره موبایل ۱۱ رقمی که با ۰۹ شروع می‌شود وارد کنید."
)

C8_ASK_ADDRESS = "نشانی کامل پستی را در یک پیام بنویسید:\n\nاستان، شهر، خیابان، کوچه، پلاک و واحد"
C8_ASK_POSTAL_CODE = "کد پستی ۱۰ رقمی را وارد کنید:"
C8_ERROR_ADDRESS_TOO_SHORT = (
    "نشانی وارد شده کوتاه است. لطفاً نشانی کامل شامل شهر، خیابان و پلاک را بنویسید."
)
C8_ERROR_INVALID_POSTAL_CODE = "کد پستی باید دقیقاً ۱۰ رقم باشد."

C9_INVOICE = (
    "🧾 <b>پیش‌فاکتور</b>\n\n" + ORDER_CODE_LINE + "\n" + DATE_LINE + "\n\n"
    "{items_block}\n"
    "هزینه ارسال — {shipping_cost}\n" + DIVIDER + "\n"
    "مبلغ قابل پرداخت:\n"
    "<b>{payable_amount}</b>\n\n"
    "⚠️ لطفاً دقیقاً همین مبلغ را واریز کنید. سه رقم آخر برای شناسایی پرداخت شما ثبت شده است.\n\n"
    "شماره کارت:\n"
    "<code>{card_number}</code>\n"
    "به نام: {card_holder}\n\n"
    "مهلت پرداخت: تا {payment_window_hours} ساعت آینده"
)
C9_ITEM_LINE = "{product_name} × {quantity} — {line_total}"

C10_ASK_RECEIPT = (
    "تصویر فیش واریزی را ارسال کنید.\n\nمبلغ، تاریخ و شماره پیگیری باید در تصویر خوانا باشد."
)
C10_ERROR_WRONG_FILE_TYPE = (
    "فقط تصویر فیش قابل بررسی است. لطفاً از فیش عکس بگیرید یا اسکرین‌شات بفرستید."
)
C10_ERROR_DUPLICATE_IMAGE = (
    "این تصویر قبلاً برای سفارش دیگری ارسال شده است. لطفاً فیش مربوط به همین سفارش را بفرستید."
)

C11_AWAITING_APPROVAL = (
    "✅ فیش شما ثبت شد.\n\n" + ORDER_CODE_LINE + "\nوضعیت: در انتظار تأیید پرداخت\n\n"
    "نتیجه بررسی از همین‌جا به شما اطلاع داده می‌شود."
)

C12_DELIVERY = (
    "🎉 پرداخت شما تأیید شد.\n\n"
    "سفارش شما آماده است — {product_name}:\n"
    "━━━━━━━━━━━━\n"
    "<code>{credential_payload}</code>\n"
    "━━━━━━━━━━━━\n\n"
    "این اطلاعات را نزد خود نگه دارید."
)
C12_INVOICE = (
    "🧾 <b>فاکتور فروش</b>\n\n" + ORDER_CODE_LINE + "\n"
    "تاریخ: {datetime}\n"
    "خریدار: {buyer_name}\n\n"
    "{items_block}\n" + DIVIDER + "\n"
    "پرداخت‌شده: {paid_amount} ✅\n\n"
    "از خرید شما سپاسگزاریم."
)

C13_APPROVED_PHYSICAL = (
    "✅ پرداخت شما تأیید شد و سفارش نهایی شد.\n\n"
    + ORDER_CODE_LINE
    + "\nوضعیت: در حال آماده‌سازی\n\n"
    "به محض ارسال، کد رهگیری پستی از همین‌جا برای شما فرستاده می‌شود."
)
C13_SHIPPED = (
    "📮 سفارش شما ارسال شد.\n\n" + ORDER_CODE_LINE + "\n"
    "کد رهگیری: <code>{tracking_number}</code>\n"
    "شرکت ارسال: {carrier}\n\n"
    "پیگیری مرسوله: {tracking_url}"
)

C14_REJECTED = (
    "❌ پرداخت شما تأیید نشد.\n\n" + ORDER_CODE_LINE + "\nدلیل: {reason}\n\n"
    "می‌توانید فیش صحیح را دوباره ارسال کنید."
)
C14_REPEAT_REJECTION_SUFFIX = "در صورت نیاز با پشتیبانی در تماس باشید."

C15_HISTORY_HEADER = "📦 <b>سفارش‌های شما</b>"
C15_HISTORY_ROW = "<code>{order_code}</code> — {date} — {status_label}"
C15_EMPTY_HISTORY = "هنوز سفارشی ثبت نکرده‌اید."
C15_EXPIRED_NOTICE = (
    "⌛️ مهلت پرداخت سفارش <code>{order_code}</code> به پایان رسید و سفارش لغو شد.\n\n"
    "در صورت تمایل می‌توانید دوباره سفارش خود را ثبت کنید."
)

# ── 4. Owner screens O1–O6 ──────────────────────────────────────────────
O1_NEW_RECEIPT = (
    "🔔 <b>فیش جدید — نیازمند بررسی</b>\n\n" + ORDER_CODE_LINE + "\n"
    "مشتری: {customer_name}\n"
    "تماس: <code>{phone}</code>\n"
    "مبلغ فاکتور: <b>{payable_amount}</b>\n"
    "زمان: {datetime}\n\n"
    "اقلام:\n"
    "{items_block}"
)
O1_ITEM_LINE = "• {product_name} × {quantity}"
O1_DUPLICATE_WARNING = "⚠️ این تصویر قبلاً برای سفارش <code>{other_order_code}</code> ارسال شده است."
O1_OUTCOME_APPROVED_SUFFIX = "✅ تأیید شد — {time}"
O1_OUTCOME_REJECTED_SUFFIX = "❌ رد شد — {time}"

O2_REASON_PROMPT = "دلیل رد سفارش <code>{order_code}</code> را انتخاب کنید:"
O2_CUSTOM_REASON_PREFIX = "دلیل:"

O3_APPROVED_DIGITAL = "✅ سفارش <code>{order_code}</code> تأیید شد.\n\n{items_block}"
O3_APPROVED_DIGITAL_ITEM_LINE = (
    "{product_name}: {delivered_qty} کد تحویل داده شد — موجودی باقی‌مانده: {remaining_stock}"
)
O3_STOCK_EXHAUSTED_WARNING = (
    "⚠️ سفارش <code>{order_code}</code> تأیید شد اما موجودی «{product_name}» تمام شده "
    "و تحویل انجام نشد.\n\nمشتری در انتظار است."
)
O3_APPROVED_PHYSICAL = (
    "✅ سفارش <code>{order_code}</code> تأیید شد. پس از ارسال مرسوله، کد رهگیری را ثبت کنید."
)

O4_PANEL_ROOT = (
    "⚙️ <b>پنل مدیریت</b>\n\n"
    "⏳ در انتظار تأیید: {pending_count} سفارش\n"
    "📦 در حال آماده‌سازی: {preparing_count} سفارش\n"
    "🔑 موجودی رو به اتمام: {low_stock_count} محصول"
)

O5_TRACKING_PROMPT = "کد رهگیری پستی سفارش <code>{order_code}</code> را وارد کنید:"
O5_ERROR_INVALID_TRACKING = "کد رهگیری باید بین ۱۰ تا ۲۴ رقم باشد."
O5_TRACKING_SAVED = "✅ کد رهگیری ثبت و برای مشتری ارسال شد."

O6_CUSTOMER_PROMPT = "پیام خود را بنویسید. پیام شما مستقیماً برای فروشنده ارسال می‌شود."
O6_CUSTOMER_SENT_CONFIRMATION = "✅ پیام شما ارسال شد."
O6_SUPPORT_RELAY = (
    "💬 پیام پشتیبانی\n\n"
    "از: {customer_name} — <code>{phone}</code>\n"
    "آخرین سفارش: <code>{last_order_code}</code>\n\n"
    "«{message_text}»"
)
O6_REPLY_PREFIX = "💬 پاسخ پشتیبانی:"

# ── 5. Errors E1–E9 ──────────────────────────────────────────────────────
E1_USE_BUTTONS = "لطفاً از دکمه‌های زیر استفاده کنید."
E2_ALREADY_PROCESSED = "این سفارش قبلاً بررسی شده است."
E3_PRODUCT_REMOVED = "«{product_name}» دیگر موجود نیست و از سبد شما حذف شد."
E4_PRICE_CHANGED = "قیمت برخی اقلام سبد شما به‌روز شد. لطفاً سبد را دوباره بررسی کنید."
E5_STOCK_REDUCED = (
    "موجودی «{product_name}» کمتر از تعداد درخواستی شماست. تعداد به {new_quantity} کاهش یافت."
)
E6_STATE_LOST = "ادامه مرحله قبل ممکن نیست. لطفاً دوباره شروع کنید."
E7_OWNER_BLOCKED_ALERT = (
    "⚠️ ارسال پیام به مشتری سفارش <code>{order_code}</code> ممکن نشد — ربات مسدود شده است."
)
# The spec describes E8's *behavior* (retry 3x, then alert, hold state)
# but gives no literal string — unlike every other error here, this one
# is authored, not transcribed, and needs the same native-speaker
# review the rest of this file does before ship.
E8_SEND_FAILED_ALERT = (
    "⚠️ ارسال پیام برای سفارش <code>{order_code}</code> با خطا مواجه شد و پس از تلاش مجدد "
    "ناموفق بود — سفارش در وضعیت فعلی باقی مانده است."
)
E9_UNKNOWN_COMMAND = "دستور نامعتبر است. برای شروع /start را بزنید."

# ── 6. REJECT_REASONS ────────────────────────────────────────────────────
# (key, owner_button_label, customer_sentence). The owner's terse chip
# and the customer's polite sentence are different strings on purpose
# (O2's own spec note) — never reuse one for the other. "custom" has no
# customer_sentence: the owner types free text (<= 200 chars), sent
# verbatim after O2_CUSTOM_REASON_PREFIX.
REJECT_REASONS: tuple[tuple[str, str, str | None], ...] = (
    ("amount_mismatch", BTN_REASON_AMOUNT_MISMATCH, "مبلغ واریزی با مبلغ فاکتور مطابقت ندارد."),
    ("unreadable", BTN_REASON_UNREADABLE, "تصویر فیش خوانا نیست."),
    ("duplicate", BTN_REASON_DUPLICATE, "این فیش قبلاً استفاده شده است."),
    ("not_recorded", BTN_REASON_NOT_RECORDED, "واریزی در حساب ثبت نشده است."),
    ("custom", BTN_CUSTOM_REASON, None),
)

# ── 7. STATUS_LABELS ──────────────────────────────────────────────────────
STATUS_LABELS: dict[OrderState, str] = {
    OrderState.DRAFT: "⏳ در انتظار پرداخت",  # never persisted; present only for completeness
    OrderState.AWAITING_RECEIPT: "⏳ در انتظار پرداخت",
    OrderState.RECEIPT_SUBMITTED: "⏳ در انتظار تأیید",
    OrderState.APPROVED: "📦 در حال آماده‌سازی",
    OrderState.REJECTED: "⛔️ نیاز به ارسال مجدد فیش",  # not one of the spec's six; see docstring
    OrderState.CANCELLED: "❌ لغو شده",
    OrderState.EXPIRED: "❌ لغو شده",
    OrderState.FULFILLED: "✅ تحویل‌شده",
}

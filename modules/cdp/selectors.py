"""Givex/Lush USA — URL targets and CSS selectors.

Single source of truth for all page URLs and CSS selectors used in the
eGift card purchase flow. Defined in blueprint order (§3 → §4 → §5).
Any driver implementation MUST import from this module instead of
hard-coding strings.
"""

# ── §3 Khởi tạo & Điều hướng ─────────────────────────────────────────────────

# Base URL of the Lush USA Givex portal
URL_HOME = "https://wwws-usa2.givex.com/cws4.0/lushusa/"

# Geo-check endpoint (pre-flight, §2)
URL_GEO_CHECK = "lumtest.com/myip.json"

# Cookie consent banner — accept button (only if banner appears)
SEL_COOKIE_ACCEPT = "#button--accept-cookies"

# "Buy E-Gift Cards" navigation button on home page
SEL_BUY_EGIFT = "#cardForeground a[href*='Buy-E-gift-Cards']"

# ── §4 Trang tạo eGift (EGIFT_PAGE) ──────────────────────────────────────────

# eGift creation form page
URL_EGIFT_PAGE = "https://wwws-usa2.givex.com/cws4.0/lushusa/e-gifts/"

# Form fields — eGift creation
SEL_GREETING_MSG   = "#cws_txt_gcMsg"        # Greeting / lời chúc (random)
SEL_AMOUNT         = "#cws_txt_gcBuyAmt"     # Amount / số tiền
SEL_RECIPIENT_NAME = "#cws_txt_gcBuyTo"      # To — Recipient Name
SEL_RECIP_EMAIL    = "#cws_txt_recipEmail"   # Recipient Email
SEL_CONFIRM_EMAIL  = "#cws_txt_confRecipEmail"  # Confirm Recipient Email
SEL_FROM_NAME      = "#cws_txt_gcBuyFrom"    # From — Sender Name

# Add to cart button (inner span — bounding-box click target)
SEL_ADD_TO_CART    = "#cws_btn_gcBuyAdd > span"

# "Review & Checkout" button — wait for this to appear after add-to-cart
SEL_REVIEW_CHECKOUT = "#cws_btn_gcBuyCheckout"

# ── §4→§5 Cart & Guest Checkout ───────────────────────────────────────────────

# Shopping cart page
URL_CART = "https://wwws-usa2.givex.com/cws4.0/lushusa/e-gifts/shopping-cart.html"

# Begin checkout button on cart page
SEL_BEGIN_CHECKOUT = "#cws_btn_cartCheckout"

# Guest checkout page
URL_CHECKOUT = "https://wwws-usa2.givex.com/cws4.0/lushusa/e-gifts/checkout.html"

# Guest email input
SEL_GUEST_EMAIL    = "#cws_txt_guestEmail"

# Continue button on guest checkout
SEL_GUEST_CONTINUE = "#cws_btn_guestChkout"

# ── §5 Thanh toán (PAYMENT) ───────────────────────────────────────────────────

# Payment form page
URL_PAYMENT = "https://wwws-usa2.givex.com/cws4.0/lushusa/e-gifts/guest/payment.html"

# Card fields
SEL_CC_NAME    = "#cws_txt_ccName"       # Name shown on card
SEL_CC_NUM     = "#cws_txt_ccNum"        # Card number (16 digits, 4x4 pattern)
SEL_CC_EXP_MON = "#cws_list_ccExpMon"   # Expiry month (select)
SEL_CC_EXP_YR  = "#cws_list_ccExpYr"    # Expiry year (select)
SEL_CC_CVV     = "#cws_txt_ccCvv"       # CVV

# Billing address fields
SEL_BILLING_ADDR1    = "#cws_txt_billingAddr1"    # Address line 1
SEL_BILLING_COUNTRY  = "#cws_list_billingCountry" # Country (select)
SEL_BILLING_PROVINCE = "#cws_list_billingProvince" # State/Province (select)
SEL_BILLING_CITY     = "#cws_txt_billingCity"     # City
SEL_BILLING_POSTAL   = "#cws_txt_billingPostal"   # Zip/Postal code
SEL_BILLING_PHONE    = "#cws_txt_billingPhone"    # Phone number

# Complete purchase button — CRITICAL_SECTION trigger (§8.3, zero-delay zone)
SEL_COMPLETE_PURCHASE = "#cws_btn_checkoutPay"

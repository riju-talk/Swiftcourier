# SwiftCourier — Pages, Routes & UI Spec

A complete map of every URL, every rendered page, and a deep description of each
page's layout, components and actions. Written to hand to a design tool (Stitch)
for a redesign. Django 5.2 · templates are `.dj` (Django template syntax, custom
extension) · Tailwind CSS v4 (compiled, not the play CDN) · Alpine.js for small
interactivity · ApexCharts / simple-datatables where charts/tables need it.

---

## 1. Product in one paragraph

SwiftCourier is a **multi-courier shipping aggregator for Indian D2C / B2B
merchants**. A merchant creates orders (manually, by Excel upload, or via a
Shopify connection), the platform picks a courier from the merchant's assigned
rate cards, books the shipment, tracks it through the lifecycle via carrier
webhooks, debits a prepaid wallet for freight, and reconciles COD collections
back to the merchant. There are **three roles**, each with its own panel:

| Role | Panel | Who |
|---|---|---|
| `user` | **Merchant panel** (`/user_panel/…`) | the shipping customer |
| `admin` | **Admin panel** (`/admin_panel/…`) | a reseller / account manager over a set of merchants |
| `super_admin` | **Admin Console** (`/superadmin_panel/…`) | the platform operator |

---

## 2. Design system (current)

The look is **"operational light"** — bright, dense, precise, one red accent.
Defined in `theme/static_src/src/styles.css` (≈2,000 lines) and
`theme/static_src/tailwind.config.js`.

### Colour
| Token | Hex | Use |
|---|---|---|
| `primary` / red-600 | `#dc2626` | the single accent — links, active nav, focus rings, primary CTAs on hover, status = error |
| black / ink | `#0e1726` | primary text, primary button fill, brand wordmark first half |
| red-500 | `#ef4444` / `dc2626` | brand wordmark second half ("Courier"), auth glows |
| page ground | `#f6f6f7` (light) / `#07090f` (dark) | app canvas, with a faint radial red wash top-right |
| surface | `#ffffff` / `#0e1220` | cards / panels |
| hairline | `rgba(16,23,38,.05)` | card outline (concentric, `outline-offset:-1px`), table row borders |
| success | `#00ab55` (green-600 in newer markup) | delivered, "Activate" |
| warning | `#e2a03f` / amber-500 | NDR, cutoff banners |
| neutrals | true grey ramp (neutral-50…900) | secondary text, borders, chips |

### Type
- Font: **Plus Jakarta Sans** (headings + UI), Nunito fallback. Never Inter/Roboto.
- Base 13–14px. Headings tight (`letter-spacing:-0.02em`), `h1` ≈ 1.7rem/700.
- Table headers: 11px, uppercase, `letter-spacing:.04em`, grey.
- Section eyebrows in the sidebar: 10px, uppercase, `letter-spacing:.12em`, neutral-400.
- KPI numbers: `font-variant-numeric: tabular-nums`, tight tracking.

### Shape & depth
- Radius: cards `1rem`, buttons `0.7rem`, inputs `0.7rem`, pills `9999px`.
- Cards **float** — soft 3-layer shadow (`--shadow-card`) + a 1px concentric
  outline, no hard border. Lift `translateY(-2px)` + bigger shadow on hover for
  KPI tiles.
- Buttons: spring press (`active:scale(0.97)`), custom `cubic-bezier` easing.
- Page content fades up on load (`pv-fade-up`, 0.6s, blur→sharp).
- Sidebar has a depth shadow, not a hairline. Header sits on frosted glass.

### Component vocabulary (utility classes already in the CSS)
`.panel` (floating white card), `.btn` + `.btn-primary` (black→red) / `.btn-outline-primary` / `.btn-secondary` / `.btn-success` / `.btn-danger` (+ `.btn-sm` `.btn-lg`), `.badge` + `.badge-outline-*`, `.form-input` / `.form-select` / `.form-textarea` / `.form-checkbox` / `.form-radio` (red focus ring), `.table-responsive` / `.table-hover` / `.table-striped`, `.dropdown`.

### What a redesign should keep
- The **two-panel auth identity** (below) — it's the front door and is already good.
- Red/black/white. One accent only.
- Dense data tables (merchants live in them all day).
- The status-pill vocabulary mapped to order statuses.

### What a redesign should fix (known inconsistencies)
- Several pages still use rogue colours: `analytics.dj` cyan/teal gradient tiles;
  `mis.dj` emerald/cyan buttons; `billing.dj` `btn-red-600` (not a real class);
  gradient KPI cards. Everything should be red/black/white.
- Table markup is copy-pasted per page (9 near-identical shipment tables) — should
  become one component.
- Border colours are a mix of `border-white`, `border-neutral-200`,
  `border-gray-200`, `dark:border-white/10` — normalise.
- Dark mode is inconsistently wired; some pages assume light only.

---

## 3. Global shell

### 3.1 Auth layout — `templates/components/layouts/auth_layout.dj`
Used by every signed-out screen. Full-bleed, no chrome. A brief black screen-loader
with a pulsing white `S` mark. Loads the compiled CSS, Font Awesome, Plus Jakarta.

**The auth pattern (all auth pages follow it):** a `lg:grid lg:grid-cols-2`, full height.
- **Left (hidden below `lg`): brand panel.** Solid black. Two blurred red radial
  glows (top-left `bg-red-600/20`, bottom-right `bg-red-700/10`). Top: `Swift`
  (white) + `Courier` (red-500) wordmark, 2xl/800, and a `LOGISTICS PLATFORM`
  eyebrow (10px, `tracking-[0.3em]`, white/40). Middle: a big 3xl–4xl/700 headline
  + a white/60 paragraph + a 3-column stat grid on a top hairline
  (`Couriers 15+` / `Tracking Real-time` / `Support 24/7`). Bottom: a "SHIP WITH"
  label + a 4-col grid of courier-name chips (`bg-white/5 ring-1 ring-white/10`,
  h-11), OR (super-admin) a small "restricted access" note.
- **Right: white form panel.** Centred, `max-w-sm`. Mobile-only wordmark at top.
  An `h2` (2xl/700) + a one-line `text-sm text-neutral-500` subtitle. The form:
  stacked fields, each a `label` (13px/500) over an `input`
  (`rounded-lg border-neutral-300 px-3.5 py-2.5 text-sm`,
  `focus:border-red-600 focus:ring-2 focus:ring-red-600/20`). Password fields have
  an eye-toggle button inset right. Primary button: full width,
  `rounded-lg bg-black px-4 py-2.5 text-sm font-semibold text-white hover:bg-red-600`.
  A `text-sm text-neutral-500` line below with a cross-link (`text-red-600`).

### 3.2 App layout — `templates/components/layouts/layout.dj`
Every signed-in page. Structure:
- Screen-loader (pulsing black `S` chip on the page ground) shown until JS boots.
- A scroll-to-top FAB, bottom-right, `btn-outline-primary rounded-full` — appears after 50px scroll.
- A one-time **agreement popup** (`components/common/user_panel_agreement_popup.dj`)
  — a centred modal "Agreement Required / Please accept the agreement…" with
  *Remind me later* (ghost) and *Accept Now* (red) → KYC. Only shows when a
  `?show_agreement_accept_popup=true` param is present.
- `.main-container` → **sidebar** (role-switched include) + `.main-content`
  (header + `p-4 sm:p-6` content slot + footer).
- Footer: `© 2026 SwiftCourier. All rights reserved.` (wordmark in it).

### 3.3 Sidebar — `<role>_panel/…/components/common/sidebar.dj`
Fixed left, 260px, white, depth shadow. **Collapsible-vertical** behaviour: on
`lg+` it sits as a **72px icon rail**; hovering it (or toggling) expands to 264px
with labels. Toggled state persists (Alpine `$persist`).

- **Brand row** (px-4 py-3): a black `S` chip (h-8 rounded-lg) + `Swift`+`Courier`
  wordmark (2xl/800). A `‹` collapse chevron on the right.
- **Nav list** (`perfect-scrollbar`, `font-semibold`, `space-y-0.5`): grouped
  under uppercase section `<h2>` eyebrows. Each item is a `nav-link`: a 40px row,
  `rounded-md`, 13px, an 18px 1.5-stroke icon + label; hover = light grey fill;
  **active = red-50 fill + red-700 text + a 3px red bar off the left edge**
  (in the collapsed rail the active item becomes a solid red chip with a white
  icon). Expandable items have a `›` chevron that rotates 90° and reveal a
  `sub-menu` (indented, a left hairline, no icons, 36px rows, red active text).

**Merchant sidebar groups & items** (`user_panel/…/sidebar.dj`):
- *Dashboard* → Dashboard
- *Order Management* → Orders ▸ [B2C Order, Reverse Order]; Shipments ▸ [Manage Shipment, Weight Discrepancies, NDR]
- *Reports* → MIS
- *Finance* → Finance ▸ [Shipping Charges, COD Remittance, All Recharges, Wallet History, Invoice]
- *Tools* → Rate Card, Rate Calculator, Pincode Serviceability, Channels ▸ [Shopify] (Channels partly wired)
- (Settings — KYC / Label / Printer / Courier Rules — reachable via the profile menu / direct URLs)

**Admin Console sidebar** (`superadmin_panel/…/sidebar.dj`):
- Dashboard
- *Courier Management* → Courier Settings ▸ [API Integration, Rate Card, Send Notification]
- *Admin* → All About Admins ▸ [Admin Lists, Add Admin]
- *Client* → Client ▸ [Client Details]
- *Pincode* → Pincode Manage

**Admin panel sidebar** (`admin_panel/…/sidebar.dj`): Dashboard, All Users.

### 3.4 Header — `templates/components/common/header.dj` (shared by all roles)
Sticky, h-14, frosted white (`bg-white/85 backdrop-blur`), bottom hairline.
- Left: on mobile, the wordmark + a hamburger that toggles the sidebar. On `md+`,
  a **"Welcome, {name}!"** line (bold 13px) over a live **date** ("Sunday, 30th
  August 2026", JS-formatted). Name = company/full name, else "Admin" for admin
  roles, else the email.
- Right cluster (all 36px, `rounded-lg border-neutral-200` icon buttons):
  1. **Wallet chip** *(merchant only)* — a pill: a red ₹ glyph + the balance
     (`{{ balance|floatformat:-2 }}`) + a `+` in a grey square that turns black on
     hover; links to `/wallet/add-money/`.
  2. **Theme toggle** — cycles light / dark / system (sun / moon / monitor icon).
  3. **Notifications** — bell → dropdown (`components/common/notifications.dj`),
     shows unread count + last 5, "see all" → `/account/notifications/`.
  4. **Activity** — a doc icon with a pulsing green dot → dropdown of last 5
     activities → `/account/activities/`.
  5. **Profile** — a black circular avatar with the user's initial. Dropdown:
     header row (avatar + name + `shipzee_code` chip like `SCU265257` + email),
     then Profile, Notifications, Change Password, Settings, and a bordered
     **Sign Out** (red).

### 3.5 Toasts — `templates/components/common/messages.dj`
Django messages render as **stacked toasts**, top-right (`fixed inset-x-3 top-3`,
`sm:right-4 sm:max-w-sm`). Each: a white card, hairline, `shadow-lg`, a coloured
4px left bar + a matching 6px icon chip (green check / amber triangle / red X /
neutral info), an UPPERCASE tag label + the message, a dismiss X, and a 5s
shrinking progress bar (pauses on hover). Slide-in from the right.

### 3.6 Error pages — `templates/{400,403,404,500}.dj` (+ `components/errors/base.dj`)
**Self-contained** (no layout, no DB — a 500 renders even if the DB is down).
Full black screen, two blurred red glows, centred `max-w-30rem` column:
`S`+`Swift`+`Courier` mark, a huge translucent gradient number (`404` …), an
uppercase eyebrow, a `1.6rem/700` heading, a `0.95rem` white/60 line, and 1–2
buttons (white `Back to dashboard` that goes red on hover, ghost secondary like
`Track a shipment` / `Try again`). 500 also shows a `Reference <id>` line if
present. `noindex`.

---

## 4. Full route table

Legend: **P** = renders a full HTML page · **A** = JSON/API · **H** = webhook (POST-only) · **X** = action handler (POST → redirect) · **F** = file download.

### Public / root
| Method-ish | URL | name | View | Notes |
|---|---|---|---|---|
| P/redirect | `/` | `index` | `swiftcourier.views.index` | bounces to the right dashboard by role, or to signin |
| P | `/track-shipment/?awb_number=` | `track-shipment` | `track_shipment` | public AWB tracker — timeline of past/current/future statuses |
| A | `/subscribe_newsletter/?email=` | `subscribe-newsletter` | — | marketing-site newsletter opt-in |
| A | `/contact_us/` | `contact-us` | — | marketing-site contact / quote form |

### Auth — `/account/…`
| | URL | name | View | |
|---|---|---|---|---|
| P | `/account/signin/` | `signin` | `signin` | merchant + admin sign-in (role dropdown) |
| P | `/account/superadmin-signin/` | `superadmin_signin` | `superadmin_signin` | Admin Console sign-in |
| P | `/account/signup/` | `signup` | `Signup` (CBV) | merchant self-registration |
| P | `/account/verify/` | `verify_email` | `VerifyEmail` | OTP email verification |
| X | `/account/verify/send-otp/` | `send_verification_otp` | `SendVerificationOtp` | resend OTP |
| P | `/account/forget-password/` | `forget_password` | `ForgetPassword` | request a reset link |
| P | `/account/reset/password/<id>/<token>/` | `reset_password` | `ResetPassword` | set a new password from an emailed link (token is a UUID) |
| X | `/account/signout/` | `signout` | `Signout` | |
| P | `/account/change-password/` | `change-password` | `change_password` | in-app, requires current password |
| X | `/account/update-password/<user_id>/` | `update-password` | `update_password` | admin-set password |
| P | `/account/profile/` | `profile` | `profile` | account profile |
| P | `/account/notifications/` | `notifications` | `notifications` | full notification list (unread first) |
| P | `/account/activities/` | `activities` | `activities` | full activity/audit list |
| X | `/account/save-label-setting/` | `save_label_setting` | — | |

### Merchant panel — `/user_panel/…` (role `user`)
| | URL | name | View | Page |
|---|---|---|---|---|
| P | `/user_panel/dashboard/` | `dashboard` | `dashboard` | **Sales dashboard** (renders `dashboard_new.dj`) |
| P | `/user_panel/analytics/` | `analytics` | `analytics` | **Analytics** — charts + courier/date tables |
| P | `/user_panel/mis/` | `mis` | `mis` | **MIS reports** — tabbed report tables + export |
| A | `/user_panel/statistics/` | `statistics` | `statistics` | JSON feed for the dashboard charts |
| P | `/user_panel/shipment/<status>/` | `shipment` | `shipment` | **Shipment list** — one page, 10 status tabs (`ready_to_ship`, `processing`, `pending_pickup`, `in_transit`, `out_for_delivery`, `delivered`, `rto`, `cancelled`, `all_orders`, + `failed`) |
| P | `/user_panel/order/add-order/` | `add-order` | `add_order` | **Create Shipment** (renders `b2c_order.html`) — Single Order / Bulk Upload tabs |
| P | `/user_panel/order/add-order-new/` | `add-order-new` | `add_order_new` | alternate add-order (`add_order.dj`) |
| P | `/user_panel/order/add-reverse-order/` | `add-reverse-order` | `add_reverse_order` | **Create Reverse (return) Shipment** |
| P | `/user_panel/order/failed-order/` | `failed-order` | `failed_order` | orders that failed to book |
| P | `/user_panel/order/cancelled-order/` | `cancelled-order` | `cancelled_order` | cancelled orders list + export |
| P | `/user_panel/order/details/<id>/` | `order-details` | `order_details` | **Order invoice** — ship-to, items table, reconciled totals |
| P | `/user_panel/weight-discrepancies/` | `weight-discrepancies` | `weight_discrepancies` | carrier re-weigh disputes + filters + submit form |
| P | `/user_panel/ndr/` | `ndr` | `ndr` | NDR (non-delivery) queue + action modal |
| P | `/user_panel/finance/shipping-charges/` | `shipping-charges` | `shipping_charges` | per-shipment freight ledger + export |
| P | `/user_panel/finance/cod-remittance/` | `cod-remittance` | `cod_remittance` | COD payout table |
| F | `/user_panel/finance/cod-remittance/download-file/<id>/` | `download-cod-remittance-file` | — | payout CSV |
| P | `/user_panel/finance/all-recharges/` | `all-recharges` | `all_recharges` | wallet top-up history |
| P | `/user_panel/finance/wallet-history/` | `wallet-history` | `wallet_history` | full wallet ledger (credit/debit/closing) |
| P | `/user_panel/finance/invoices/` | `invoices` | `invoices` | platform invoices to the merchant |
| P | `/user_panel/finance/rate-card/` | `rate-card` | `rate_card` | the merchant's assigned rate cards, read-only |
| P | `/user_panel/tools/rate-calculator/` | `tool-rate-calculator` | `tool_rate_calculator` | **Rate Calculator** — quote across the merchant's cards |
| P | `/user_panel/tools/pincode-serviceability/` | `tool-pincode-serviceability` | `tool_pincode_serviceability` | **Pincode Serviceability** checker |
| P | `/user_panel/all-hub/` | `all-hub` | `all_hub` | **Warehouse list** |
| P | `/user_panel/add-hub/` | `add-hub` | `add_hub` | **Add / edit a warehouse** |
| X | `/user_panel/edit-hub/` `…/deactivate-hub/` `…/make-primary-hub/` | | | hub row actions |
| P | `/user_panel/billing/` | `billing` | `billing` | **Billing** — 6 stacked ledger tables |
| P | `/user_panel/setting/kyc/` | `kyc` | `kyc` | **KYC** — stepper + document upload |
| P | `/user_panel/setting/label/` | `label` | `label` | **Label settings** — many toggles for what shows on the shipping label |
| P | `/user_panel/setting/printer/` | `printer` | `printer` | **Label page size** radio group |
| P | `/user_panel/setting/courier-rules/` | `courier-rules` | `courier_rules` | **Courier priority** — drag-to-reorder preference list |
| P | `/user_panel/setting/invoice/` | `invoice` | `invoice` | invoice settings (stub) |
| P | `/user_panel/integration/shopify/` | `shopify-integration` | `shopify_integration` | **Shopify** — connect a store, per-store order tabs |
| P | `/user_panel/view-label/<order_id>/` | `view-label` | `view_label` | printable shipping label |
| P | `/user_panel/view-invoice/<order_id>/` | `view-invoice` | `view_invoice` | printable tax invoice |
| A/F | `/user_panel/api/labels/`, `/api/ats-label-proxy/`, `/download-label/`, `/download-label-old/`, `/download-invoice/`, `/get-awb-details/` | | | label/PDF plumbing |

### Order actions — `/order/…` (POST → redirect)
| | URL | name | Does |
|---|---|---|---|
| X | `/order/save/single-order/` | `save-single-order` | create one order from the Add-Order form |
| X | `/order/save/bulk-order/` | `save-bulk-order` | ingest an uploaded Excel of orders |
| X | `/order/ship-order/` | `ship-order` | send selected orders to `processing` and queue the async ship batch (charges the wallet, books the carrier). Rolls back to `ready_to_ship` if the broker is down. |
| X | `/order/cancel-order/<id>/` | `cancel-order` | cancel a `ready_to_ship` order, or cancel the carrier booking on a `pending_pickup` order + refund + back to `ready_to_ship`. Non-cancellable states are rejected with a message. |
| X | `/order/cancel-bulk-order/` | `cancel-bulk-order` | bulk version |
| X | `/order/order-edit-clone/<id>/<edit|clone>/` | `order-edit-clone` | edit or duplicate an order |
| F | `/order/download-manifest/` | `download-manifest` | pickup manifest PDF |
| F | `/order/download-failed-bulk-orders/<key>/` | `download-failed-bulk-orders` | error report for a bulk upload |
| H | `/order/wordpress/order-created/<user_id>/` | `wordpress-order-created` | WooCommerce order webhook |

### Wallet / payments — `/wallet/…`
| | URL | name | |
|---|---|---|---|
| P | `/wallet/add-money/` | `add-money` | **Add Money** card (presets + amount → Razorpay) |
| X | `/wallet/checkout/` `…/create-razorpay-transaction/` `…/verify-razorpay-transaction/` `…/callback/` | | payment-gateway plumbing |
| P/X | `/wallet/redirect/<merchant_txn_id>/` | `redirect` | PhonePe return URL — verifies + credits, then → dashboard |

### Admin panel — `/admin_panel/…` (role `admin`)
| | URL | name | Page |
|---|---|---|---|
| P | `/admin_panel/dashboard/` | `dashboard` | small "Users Info" table + two "See More" cards |
| P | `/admin_panel/all-users/` | `all-users` | the admin's merchants list |
| P | `/admin_panel/user/demo/` | `user-details` | a merchant detail / billing-style profile |

### Admin Console — `/superadmin_panel/…` (role `super_admin`)
| | URL | name | Page |
|---|---|---|---|
| P | `/superadmin_panel/dashboard/overview/` | `dashboard` | **Dashboard Overview** — 7 count tiles + Courier Performance + Attention Required |
| P | `/superadmin_panel/dashboard/client/` | `dashboard-client` | **All Clients Overview** — 6 tiles + client metrics/risk + a breakdown table |
| P | `/superadmin_panel/dashboard/courier-partner/` | `dashboard-courier-partner` | courier-wise performance table |
| P | `/superadmin_panel/dashboard/courier-performance/` | `dashboard-courier-performance` | courier SLA table |
| A | `/superadmin_panel/dashboard/data/` | `dashboard-data` | JSON feed for the tiles above |
| P | `/superadmin_panel/list-admin/` | `list-admin` | **All Admins** table (renders `all_admin.dj`) |
| P | `/superadmin_panel/add-admin/` | `add-admin` | **Add Admin** form (company, email, logo, mobile, password) |
| P | `/superadmin_panel/all-client/` | `all-client` | **All Users** table (email, mobile, `SCU…` code, status, View Details) |
| P | `/superadmin_panel/user-details/<user_id>/` | `user-details` | a merchant's full profile (orders, wallet, KYC, rate cards) |
| P | `/superadmin_panel/api-integration/` | `api-integration` | carrier API-key management |
| P | `/superadmin_panel/rate-card/` | `rate-card` | **Courier Rate Management** — a preview grid + "assign to users" (the assign is a static mock; real assignment is per-merchant below) |
| P | `/superadmin_panel/view-rate-cards/<user_id>/` | `view-rate-cards` | a merchant's cards |
| P | `/superadmin_panel/assign-courier-and-rates/<user_id>/` | `assign-courier-and-rates` | **Courier Rate Configuration** — add rate tables (zones × weight slabs, COD ₹/%) and save to a merchant |
| P/X | `/superadmin_panel/edit-rate-card/<id>/`, `/delete-rate-card/<id>/`, `/assign-commission/`, `/assign-admin/` | | rate-card + assignment actions |
| P | `/superadmin_panel/manage-wallet/<user_id>/` | `manage-wallet` | **Wallet Management** — balance + Add Money / Deduct Money forms (reason dropdown) |
| X | `/superadmin_panel/add-balance/<id>/`, `/deduct-balance/<id>/`, `/set-min-balance/`, `/set-debit-limit/<id>/` | | wallet actions |
| P | `/superadmin_panel/manage-pincode/` | `manage_pincode` | **Block Pincodes** — textarea + reason chips + Block; a "Blocked Pincodes" list |
| X | `/superadmin_panel/block-pincodes/`, `/unblock-pincodes/` | | pincode actions |
| P | `/superadmin_panel/send-notification/` | `send_notification` | **Send Notification** — message textarea + audience + a "Previous Notifications" list with Edit/Delete |
| X | `/superadmin_panel/change-client-status/<client_id>/` | `change_client_status` | activate / deactivate a merchant |
| A | `/superadmin_panel/get-users/` | `get_users` | user search feed |

### Shopify — `/shopify/…`
OAuth (`/auth/install`, `/auth/callback`, `/auth/uninstall`), webhooks
(`/webhooks/orders/{created,updated,cancelled,paid}`, `/webhook/orders/`,
`/webhook/uninstall/`), and a few internal pages (`/dashboard/`, `/merchants/`,
`/orders/`, `/orders/<shopify_id>/`, `/merchants/<pk>/sync/`).

### Carrier webhooks (all **POST-only**, `/…-integration/webhook/`)
`xpressbees`, `lastmiles`, `purple-drone`, `parcelx`, `sr` (Shiprocket),
`jiffy`, `fship`, `rapidshyp`, `rapidshyp-new`, `nimbuspost`, `smartship`,
`bdl`, `zippyy` — each maps a carrier status payload to an internal
`Order.update_status()` and logs a `CarrierWebhookEvent`.

### Notification delivery webhooks
`/whatsapp-integration/webhook/`, `/sms-integration/webhook/` — Twilio
delivery-status callbacks.

### Serviceability / rate API — `/api/…`
| A | `/api/serviceability/check-serviceability/` | POST pincode pair → which carriers serve it |
| A | `/api/serviceability/warehouses/` | the merchant's hubs |
| A | `/api/serviceability/dashboard-data/` | serviceability widget feed |
| A | `/api/serviceability/health/` | health check |
| A | `/api/calculator/` | POST weight/dims/pincodes → rate quotes across the merchant's cards (used by the Rate Calculator page) |

### Dev-only
`/sentry-debug/` — raises on purpose, only registered when `DEBUG=True`.

---

## 5. Page-by-page spec

> Every panel page sits inside the app shell (§3.2–3.5): fixed sidebar, sticky
> header, `p-4 sm:p-6` content slot, footer, page fade-up on load. The
> descriptions below cover **only the content slot**.

### 5.1 Auth pages

**Sign in** — `/account/signin/` · `account/signin.dj`
The auth pattern (§3.1). Left brand panel: headline *"One dashboard for every
courier you ship with."*, courier chips. Right form: `h2` "Welcome back",
subtitle "Sign in to manage your shipments". Fields: **Email**, **Password**
(eye-toggle), **Sign in as** `<select>` (User / Admin). A right-aligned
*Forgot password?* link (red). Button "Sign in". Footer: "Don't have an
account? **Sign up**".

**Sign up** — `/account/signup/` · `account/signup.dj`
Same pattern. Left headline *"Start shipping smarter in minutes."*, stats
`Couriers 15+` / `Setup Minutes` / `Support 24/7`. Right: "Create your account" /
"Enter your details to get started". Fields: **Full name**, **Email**,
**Contact number**, **Password** (eye-toggle), **Confirm password**. Button
"Create account". Footer: "Already have an account? **Sign in**".

**Admin Console sign in** — `/account/superadmin-signin/` · `account/superadmin_signin.dj`
Same pattern. Left: a `● SUPER ADMIN` pill, headline *"The command centre for the
whole network."*, stats `Merchants Unlimited` / `Couriers 15+` / `Control Full`,
and a small "Restricted access … all sign-ins are logged" note (no courier chips).
Right: `h2` "Admin Console" + a black `SUPER ADMIN` chip, subtitle "Sign in to
manage the platform". Fields: **Email**, **Password** (eye-toggle). Button
"Sign in to console". Footer: "Not an administrator? **Merchant sign in**".

**Forgot password** — `/account/forget-password/` · `account/forget_password.dj`
Pattern. Left headline *"Recover your account access."*. Right: a single **Email**
field + a "Send reset link" button + a "Back to sign in" link.

**Set / reset password** — `account/set_password.dj` (from the emailed link)
Pattern. Right: **New password** + **Confirm password** + "Reset password". A bad
/ expired link redirects to sign-in with a message.

**Verify email** — `account/verify_email.dj`
Pattern. Right: a 6-box OTP input + "Verify" + a "Resend code" link with a timer.

**Change password** — `/account/change-password/` · `account/change_password.dj`
*Inside the app shell* (not the auth pattern). A single centred
`max-w-md` `.panel`-style card: "Change password" / "Update your password to keep
your account secure", then **Current password**, **New password**, **Confirm new
password**, and a full-width black→red "Update password" button.

### 5.2 Merchant — Dashboard  (`/user_panel/dashboard/` · `dashboard_new.dj`)
A sales-analytics dashboard. Sections top→bottom:
1. **4 chart cards** in a row: *Total Daily Orders* (a small bar chart, Sun–Wed),
   *Top 5 Couriers* (list/bar), *COD vs Prepaid* (donut with a red ring +
   legend), *Pickup Completion* (a radial gauge % + "Pickup Completed / Pending").
2. **Filter bar**: a **Date Range** field (opens a two-month calendar modal with
   Today / Yesterday / Last 7 / Last 30 quick-buttons, prev/next month + year
   arrows, Reset / Cancel / **Apply**), a **Method** select (All / Prepaid / COD),
   a **Courier** select, and **Apply** (black→red) / **Clear** (ghost) /
   **Bulk Export** (outline) buttons. Default range = **last 30 days**
   (shown as `MM/DD/YYYY - MM/DD/YYYY`).
3. **5 KPI stat tiles**: Total Order (+ "x% vs last period" pill), Delivery Rate
   (% + MoM), In Transit (+ vs prev wk), RTO Rate (% + trend), Avg TAT (days).
4. **Status breakdown grid** — 9 tiles (ORDER_PLACED, READY_TO_SHIP, INTRANSIT,
   OUT_FOR_DELIVERY, DELIVERED, FAILED_DELIVERY, ORDER_CANCELLED, RTO, LOST): each
   an icon chip + label + sub-label + a big count + a "0%" delta. A small
   "Stats are not real time; there may be a slight delay." note.
> Redesign notes: the calendar modal is huge and bespoke — replace with a compact
> range picker. The empty charts (no shipped data) need good empty states. The
> tab-title says "Sales Analytics — Reports & Exports" which is wrong for a
> dashboard.

### 5.3 Merchant — Analytics  (`/user_panel/analytics/` · `analytics.dj`)
1. **4 gradient KPI banners** (currently cyan + 3 red gradients — *should be
   flat*): headline metrics.
2. **6 small stat panels**: Total Orders, Pickup Pending, In Transit, OFD,
   Delivered, RTO.
3. **2 large chart panels** (ApexCharts): a trend area/line and a second chart.
4. **2 chart panels side-by-side**: *Sales By Courier*, *Zone Wise Load*.
5. **A chart panel** + **Courier Wise Status** table (Courier, Total, Unshipped,
   Pending, Transit, Delivered %, RTO) and a **Date Wise Summary** table (Date,
   No. of Packets, Pickup Pending, In Transit, Delivered, RTO).

### 5.4 Merchant — MIS  (`/user_panel/mis/` · `mis.dj`)
A tabbed report page. **Tab bar** (underline tabs): Daily Summary · Top NDR
Reasons · Product Wise Summary · Courier Wise Summary. A **filter bar** with a
date-range modal (same bespoke calendar as the dashboard) + **Apply** (emerald —
*should be red/black*) / **Clear** (red) / **Bulk Export** (cyan — *fix*).
Each tab is a wide data table:
- *Daily Summary*: Date, Total Orders, Pending Pickup, In Transit, Out For
  Delivery, Delivered, Exception, RTO, RTO Delivered.
- *Top NDR Reasons*: Reason, Shipment Picked, In Transit, Exception, Delivered,
  RTO In-Transit, RTO Delivered.
- *Product Wise*: Product, Pending Pickup, In Transit, Exception, Delivered, RTO
  In-Transit, RTO Delivered.
- *Courier Wise*: Courier Name, Total shipped, …

### 5.5 Merchant — Shipment list  (`/user_panel/shipment/<status>/`)
The daily driver. One page, its content swapped per status tab. Wrapper is
`shipment.dj`; each status has its own body template
(`shipment/ready_to_ship.dj`, `…/in_transit.dj`, etc. — 10 of them, ~90% identical).

- **Pickup-cutoff banner** (`components/common/pickup_cutoff.dj`): a red-tinted
  strip — *"Pickup Cutoff: Pickup will happen tomorrow for all couriers."* (with
  a live countdown on some tabs).
- **Status tab bar** (`components/common/shipment_navbar.dj`): pill/text tabs with
  live counts — **All Orders (n)** · Ready To Ship (n) · Processing (n) · Pending
  Pickup (n) · In Transit (n) · OFD (n) · Delivered (n) · RTO/RTS (n) ·
  Cancelled (n). Active tab is a solid black pill.
- **Card** (`max-w-7xl`, white, hairline): header row = **{Status} title** +
  a **Search Order** input on the left; on the right, a hidden **Ship** /
  **Cancel** action button that appears when rows are selected, a **Filter**
  toggle (red-tinted pill), and an **Export** button (red).
- **Filter panel** (collapsible): a **Date Range** picker (two-month calendar
  popover with presets), plus (on some tabs) Order IDs / AWB numbers /
  Payment method / Channel / Courier inputs, and **Clear** / **Apply Filters**.
- **Table**: checkbox · CHANNEL · SWIFTCOURIER ID (`SC{id}`) · ORDER NUMBER ·
  DATE (date over time) · CUSTOMER (name over phone) · PRODUCTS (first product,
  hover tooltip for full) · QTY · AMT (₹ over PREPAID/COD) · WT (LBH) (kg over
  `l×b×h cm`) · STATUS (a pill) · ACTION.
  - **ACTION** on `ready_to_ship`: a red **Ship** button + a `⋮` menu
    (Edit, Clone, Cancel, …).
  - On shipped tabs: **Print Label**, **Invoice**, **Track**, **Re-Ship**,
    **Cancel** (context-dependent) in the `⋮` menu.
  - The **Ship** flow opens the **Ship Order modal** (§5.6).
- **Pagination**: Previous · 1 · 2 · 3 … `last` · Next, and a **rows-per-page**
  select (10 / 50 / 100 / 200 / 500). ~296 pages at 50/page for a big account.
- `processing.dj` additionally **auto-refreshes every 12s** and self-heals
  stuck orders back to `ready_to_ship`.

### 5.6 Ship Order modal
Opened from a row's **Ship** button or the bulk **Ship** action. A small centred
white card, "Ship Order" title:
- **Select Warehouse** `<select>` (the merchant's hubs) + a `+` link to Add Hub.
- **Courier Partner** `<select>` (the merchant's assigned couriers, or "According
  to Preference" — currently disabled).
- **Cancel** (ghost) · **Submit** (red).
On submit: orders → `processing`, an async batch is queued, the user lands on the
Processing tab. If the broker is down: a red toast *"Shipping is temporarily
unavailable — your orders … are back under Ready to Ship."*

### 5.7 Merchant — Add Order  (`/user_panel/order/add-order/` · `b2c_order.html`)
"Order Management" `h1`, then **Single Order** / **Bulk Upload** tabs.

**Single Order** — "Create Shipment" heading with **Save** (black) and a disabled
**Generate AWB** button top-right; a right rail **Courier Recommendation** card
(a recommended partner + freight, currently "temporarily disabled") and a live
**Total Summary** card.
Form sections (each an `h2` with a divider):
1. **Order Information** — Order ID (+ a "generate" button, now black), Payment
   Mode (Prepaid / COD), Invoice Value ₹*, Total Value ₹*, and optional
   Shipping Charges / Tax % / Gift Wrap / COD Charges* / Other Charges / Discount.
2. **Customer Details** — Consignee name*, Company, Phone*, Alt phone, Email,
   Address*, Address 2 / landmark, Pincode* (auto-fetches City*/State*), Country
   (readonly INDIA).
3. **Products** — repeatable rows (Name, Qty, Total price, SKU, HSN) with an
   **+ Add product** button.
4. **Package Details** — Weight kg* (≥0.01), Length* / Breadth* / Height* cm (≥1).

**Bulk Upload** — a drag-and-drop Excel dropzone, a "download template" link, a
progress/result panel (`total / successful / failed`, a "download errors" link).

### 5.8 Merchant — Add Reverse Order  (`add_reverse_order.dj`, 1,811 lines)
Same shape as Add Order but for a **return pickup** (pickup = customer,
drop = the merchant's hub). Extra "reason for return" field.

### 5.9 Merchant — Order details  (`/user_panel/order/details/<id>/` · `order_details.dj`)
An invoice-style single card:
- Header: **Order Details : {order_number}**.
- Two columns: **Ship To** (name, full address, phone, email) · **Order Info**
  (SwiftCourier Order ID `SC{id}`, Order Date, Channel, Payment Type).
- **Items table**: S.No · Product · SKU · Qty · Price · Total.
- **Payment summary** (right-aligned): **Items Subtotal**, then only the non-zero
  of Discount (green −) / Gift Wrap / Other Charges / Shipping Charges / COD
  Charges / **Tax (x%)** (a computed amount, not the total), an **Adjustment**
  row if a manual total override doesn't reconcile, then a bold **Grand Total**.
- If the order has a barcode and isn't `ready_to_ship`, a small barcode image;
  order notes if any.

### 5.10 Merchant — NDR  (`/user_panel/ndr/` · `ndr.dj`)
"NDR" card. **Filter** toggle → a panel with Date Range, Order IDs, AWB numbers,
Payment method, Attempts, Channel + **Clear** / **Apply**. A table of NDR
shipments. A row action opens the **NDR Submit Form** modal: Order ID (readonly),
**Action** `<select>` (Reattempt / Update phone / Hold 24 hrs / RTO), a
conditional **re-attempt date** picker, a **Remark** textarea, Submit.
> Currently the action branches are stubs.

### 5.11 Merchant — Weight Discrepancies  (`/user_panel/weight-discrepancies/` · `weight_discrepancies.dj`)
Same shell as NDR. Filter panel adds **Product name** + **Courier**. Table of
disputes (declared vs charged weight, difference, extra charge). A row → a submit
form modal to accept / dispute.

### 5.12 Merchant — Finance pages
All share the same shape: a `.panel` card, an `h2` title, a **Search** input, an
optional **Filter** toggle, an **Export** button (red), a wide table, and
Previous/1…n/Next pagination. Some have a small ApexChart above the table.

| Page | Table columns |
|---|---|
| **Wallet History** `wallet_history.dj` | # · Date · Transaction ID · Transaction Type (credit/debit pill) · Amount · Closing Amount · Reason · Status |
| **All Recharges** `all_recharges.dj` | # · Date · Transaction ID · Amount · Closing Amount · Transaction Type · Narration · Transaction Status |
| **Shipping Charges** `shipping_charges.dj` | per-shipment freight rows (AWB, courier, weight, base/additional/COD/GST, total) + Search + Export |
| **COD Remittance** `cod_remittance.dj` | ID · Payout Date · Payout amount · Order Count · Freight Deduction · Early COD Charges % · Early COD Charges · Remittance Amount · Amount Paid · UTR · Remarks · Status · Actions (an **Export** link per row) |
| **Invoices** `invoices.dj` | Invoice # · Service · Date · Period · Amount · Action (download) |
| **Rate Card** (merchant, read-only) `finance/rate_card.dj` | "Courier Shipping Rates" — a **mode** select (Surface/Air) + **weight** select + a courier search; a big rate grid by zone (Within City / State / Metro / Rest of India / NE-J&K), a COD ₹ / COD % column; plus "Zone Definitions", "Weight Pricing", "Terms & Conditions" info panels. |

### 5.13 Merchant — Billing  (`/user_panel/billing/` · `billing.dj`)
Six stacked `.panel` cards, each a titled `simple-datatables` table with a per-row
**View** / **Download** button (currently styled `btn-red-600` / `btn-secondary` —
*normalise*): **COD Remittance**, **Invoice**, **Wallet**, **All Recharges**,
**Credit Notes**, **Weight Reconciliation**.

### 5.14 Merchant — Tools
**Rate Calculator** — `/user_panel/tools/rate-calculator/` (`components/tools/rate_calculator_*`)
"Rate Calculator" `h1` + "Compare courier pricing by pincode, weight, and payment
mode." A one-row form: **Pickup Pincode**, **Hub** (optional select),
**Destination Pincode**, **Weight (KG)**, **Dimensions L/W/H (cm)**, **Payment
Method** (Prepaid/COD), **Order Value ₹** (for COD), **Sort By** (Best Price /
Fastest), a **Calculate Rates →** button (black→red) and **Reset**.
Below: a **Courier Rates** table — Courier · Service · Chargeable Wt · ETA (a
blue "n Days" pill) · Base · Additional · COD · GST (18%) · **Total** (bold). A
"prices are estimates …" footnote.

**Pincode Serviceability** — `/user_panel/tools/pincode-serviceability/`
A pincode input (or pair) → which carriers serve it, with pickup/delivery/COD
capability and zone. (Same card style.)

### 5.15 Merchant — Warehouses
**All Hubs** — `/user_panel/all-hub/` (`hub/all_hub.dj`)
"Warehouse List" card. Top-right: **+ New Warehouse** (red outline), **Import**,
**Export**. A sortable table: ID · WAREHOUSE NAME · CONTACT PERSON (name over
phone over email) · WAREHOUSE DETAILS (address lines + city + pincode) · ACTION —
two pills per row: **Deactivate** (red outline) and **Make Primary** (green
outline; becomes a disabled green **Primary** chip when it is the primary hub).
Footer: "Showing 1 to n of n entries".

**Add / Edit Hub** — `/user_panel/add-hub/` (`hub/add_hub.dj`)
"Add a Hub" card, a single stacked form: **Hub Name** (5–20 chars), **PIN Code**,
**Phone**, **Alt phone**, **Address line 1** (textarea), **Address line 2**
(textarea), **Contact Person**, **Email**, **City**, **State**, **Country**,
**GSTIN**. A Save button.

### 5.16 Merchant — Settings
**KYC** — `/user_panel/setting/kyc/` (`setting/kyc.dj`)
A 3-step **stepper** (numbered circles + connectors). "KYC Information" section:
Name, Company name, Phone number, Email, Full address, plus document-type
selection and file uploads (PAN / GST / Aadhaar / Cancelled cheque). Submit per
step; a status badge (submitted / approved / rejected).

**Label settings** — `/user_panel/setting/label/` (`setting/label.dj`, 843 lines)
Two tabs: **Global** and **Label**. A long list of **toggle switches** for what
prints on the shipping label: show logo (+ a logo uploader), show support info
(+ support email / support mobile), hide customer mobile, hide pickup address,
hide discount, hide "powered by", hide product, hide total amount, hide weight,
hide dimension. A Save button. (A live label preview would be a good add.)

**Printer** — `/user_panel/setting/printer/` (`setting/printer.dj`)
"Label Page Size" — a **radio group** of 4 page-size options (thermal 4×6, A4,
A5, …). Save.

**Courier Rules** — `/user_panel/setting/courier-rules/` (`setting/courier_rules.dj`)
"🚚 Shipping Partner Priority" — a **drag-to-reorder** list of the merchant's
couriers; the order is the fallback preference when shipping "by preference". A
hidden `priority` field + Save.

### 5.17 Merchant — Shopify integration  (`/user_panel/integration/shopify/` · `integration/shopify.dj`)
"Shopify Integration" `h1` + **+ Add Store** button. If no stores: an empty state
("No stores connected yet" + a "Connect your store" CTA). The **connect panel**:
a `yourstore.myshopify.com` input + **Connect** (starts OAuth). Once connected:
per-store tabs, each showing that store's pulled orders in a table with a
sync/push action.

### 5.18 Public — Track shipment  (`/track-shipment/` · `track_shipment.dj`)
Public, no shell. An AWB search box; on a hit, a **vertical timeline**: past
statuses (done, with timestamps), the current status (highlighted), future
statuses (greyed). Handles forward, exception, and RTO flows. Invalid AWB → a
"not found" state.

### 5.19 Wallet — Add Money  (`/wallet/add-money/` · `wallet/add_money.dj`)
A single centred white card: "Add Money" / "Select or enter the amount you want to
add". An **Amount (₹)** input, four preset pills (**₹500 / ₹1000 / ₹2000 /
₹5000** — the selected one turns solid red), and a full-width **Add ₹{amount}**
button (black, disabled until an amount is set) that opens Razorpay checkout.

### 5.20 Admin panel
**Dashboard** — `/admin_panel/dashboard/` (`admin_panel/dashboard.dj`)
A small "Users Info" table (Name · Email · Role · Action) + two summary cards with
"See More" buttons. Minimal.

**All Users** — `/admin_panel/all-users/` (`admin_panel/all_users.dj`)
The admin's assigned merchants in a table.

**User Details** — `/admin_panel/user/demo/` (`admin_panel/user_details.dj`, 414 lines)
A profile page with Profile / Summary / "Pro Plan" / Payment History / Card
Details sections — *this is a stock billing-template layout and mostly dummy;
should be rebuilt to show real merchant data (orders, wallet, KYC, rate cards).*

### 5.21 Admin Console — Dashboards
**Overview** — `/superadmin_panel/dashboard/overview/` (`dashboard/overview.dj`)
"Dashboard Overview" / "Real-time shipment and order performance summary". **7
count tiles** in a 4+3 grid: Today So Far · Yesterday · Last 7 Days · **Last 30
Days** (label in red) · This Month · Prev Month · This Year (all start "N/A",
filled by JS from `/dashboard/data/`). Below: **Courier Performance** panel
("Unknown — 0% Delivered") and **Attention Required** panel (High NDR Rate %,
Pickup Delays, Courier Exceptions). A sub-tab bar at the top switches to the other
three dashboards.

**All Clients Overview** — `/superadmin_panel/dashboard/client/` (`dashboard/client.dj`)
**6 tiles** (Total Shipments, Pending Pickup, In Transit, Delivered, RTO, NDR) +
**Client Metrics** / **Courier Performance (Avg)** / **Risk Indicators** panels +
a **Client Shipment Breakdown** table (Client Name · Pending · In Transit ·
Delivered · RTO).

**Courier Partner** — `/…/dashboard/courier-partner/`
A single table: Courier Partner · Pending · In Transit · Delivered · RTO · NDR ·
Delivery % · Total Orders.

**Courier Performance** — `/…/dashboard/courier-performance/`
A single table: Courier Partner · Delivery % · Pickup TAT · Delivery TAT · RTO % ·
NDR % · SLA Status.

### 5.22 Admin Console — Admins & Clients
**All Admins** — `/superadmin_panel/list-admin/` (`all_admin.dj`)
"All Users" card, a **Search Users** input, a table: S No · EMAIL ID · MOBILE NO ·
**SWIFTCOURIER CODE** (`SCA…`) · ACTION (View Details), Prev/1…n/Next.

**Add Admin** — `/superadmin_panel/add-admin/` (`add_admin.dj`)
A card form: **Company Name**, **Email / Username**, **Company Logo** (file),
**Mobile Number**, **Password**, a Submit button.

**All Users (clients)** — `/superadmin_panel/all-client/` (`all_clients.dj`)
"All Users" card, **Search Users**, a table: S NO · EMAIL ID · MOBILE NO ·
**SWIFTCOURIER CODE** (`SCU…`) · STATUS (a red **Deactivate** / green **Activate**
pill toggling `change-client-status`) · CREATED ON · UPDATED ON · ACTION (**View
Details**, red). Prev/1…n/Next + a rows-per-page select.

**User Details** — `/superadmin_panel/user-details/<user_id>/` (`user_details.dj`, 596 lines)
A big merchant profile: header (name + `SCU…` code chip + join date), then
sections for orders summary, wallet, KYC status, assigned rate cards, and links to
Manage Wallet / View Rate Cards / Assign Courier & Rates for that merchant.

### 5.23 Admin Console — Rate cards
**Courier Rate Management** — `/superadmin_panel/rate-card/` (`rate_card.dj`, 873 lines)
A "Back" link, "Courier Rate Management" heading + "Export". A **Mode / Type** +
**Weight** filter + a "Search couriers" box. A big **preview grid** of couriers ×
zones (Within City / State / Metro / Rest of India / NE-J&K) with COD ₹ / COD %.
An **Assign Rates: Select Users** search + **Reset Changes** / **Save Rates**.
> This preview form is a **static mock** — real assignment is per-merchant via the
> next page. A redesign should either wire it or drop the assign section.

**Assign Courier & Rates** — `/superadmin_panel/assign-courier-and-rates/<user_id>/` (`assign_courier_and_rates.dj`, 567 lines)
"Courier Rate Configuration". An **+ Add table** button adds a rate table:
courier + mode selectors, a zone-column grid (Within City / Within State / Metro /
Rest of India / NE-J&K) with **base** and **additional** weight rate inputs, an
**Additional Weight (kg)** field, and **COD ₹** (default 30) / **COD %**
(default 1.5) inputs. A **Save** button writes all tables to that merchant.

**View Rate Cards** — `/superadmin_panel/view-rate-cards/<user_id>/` (`view_rate_cards.dj`)
"Rate Card for {email}" + a form (a stub — 32 lines).

### 5.24 Admin Console — Wallet
**Wallet Management** — `/superadmin_panel/manage-wallet/<user_id>/` (`manage_wallet.dj`)
A "Back" link, "Wallet Management" heading, the merchant name + a big
**₹ {balance}** figure. Two side-by-side cards:
- **Add Money** — Amount (`eg: 500, 1000`), a **Reason** select, an **Other
  reason** textarea (when Reason = Other), a Submit.
- **Deduct Money** — same fields.

### 5.25 Admin Console — Pincodes
**Block Pincodes** — `/superadmin_panel/manage-pincode/` (`manage_pincode.dj`)
"Block Pincodes" heading. **Enter Pincodes** input (`110011 560001 400001` —
space-separated), **Reason (Optional)** input with quick-chips (Heavy Rainfall /
Flood Alert / Road Block / Festival Rush), a **Block** button (red). Below: a
**Blocked Pincodes** list ("No blocked pincodes yet." empty state) with an
unblock action per row.

### 5.26 Admin Console — Notifications
**Send Notification** — `/superadmin_panel/send-notification/` (`send_notification.dj`)
"Send Notification" heading. A **message** textarea + an audience selector + a
Submit; an **Apply** button. A **Previous Notifications** list, each row with
**Edit** / **Delete**.

### 5.27 Admin Console — API Integration
`/superadmin_panel/api-integration/` (`api_integration.dj`, 184 lines) — "Api
Integration" card: per-carrier credential fields (token / email / password /
client id) and a save per carrier.

### 5.28 Account — Notifications / Activities
`/account/notifications/` — a list of the user's notifications, unread first, each
with a category dot, message, timestamp, and a mark-read. `/account/activities/`
— the same shape for the audit/activity log (logins, password changes, order
actions).

### 5.29 Printable — View Label / View Invoice
`/user_panel/view-label/<order_id>/` — a print-optimised shipping label (barcode,
AWB, from/to addresses, product, weight, dimensions, courier logo, a "powered by"
line) honouring the Label settings toggles. `/user_panel/view-invoice/<order_id>/`
— a print-optimised tax invoice (seller, buyer, items, GST breakup, totals).

---

## 6. Status vocabulary (for pills / timelines)

`ready_to_ship` → "Ready To Ship" · `processing` → "Processing" ·
`pending_pickup` → "Pending Pickup" · `in_transit` → "In Transit" ·
`out_for_delivery` → "Out For Delivery" · `delivered` → "Delivered" ·
`cancelled` · `lost` · `damaged` · `exception` · `ndr` · `rto` (+ the full
`rto_pending_pickup` / `rto_in_transit` / `rto_out_for_delivery` /
`rto_delivered` / `rto_cancelled` / `rto_lost` / `rto_damaged` set).
Suggested colour: green = delivered / rto_delivered; blue = in_transit /
out_for_delivery; amber = ndr / exception / pending_pickup; grey =
ready_to_ship / processing; red = cancelled / lost / damaged / rto*.

## 7. Reusable pieces a redesign should produce

- **Data table** — one component: sticky uppercase header, hairline rows, a
  checkbox column, a `⋮` row-actions menu, an empty state, a footer with
  "Showing x–y of z" + rows-per-page + pager.
- **Status pill** — status → label + colour.
- **KPI tile** — label, big tabular number, a delta pill (↑ green / ↓ red), an
  optional icon chip; hover-lifts.
- **Filter bar** — a compact date-range picker + N selects + Apply / Clear /
  Export.
- **Page header** — title + subtitle + a right-aligned action cluster.
- **Section card** (`.panel`) — title row + optional actions + body.
- **Form field** — label + control (red focus ring) + help/error text; a
  password variant with an eye toggle.
- **Modal** — centred card, title, body, a right-aligned Cancel (ghost) /
  Confirm (red or black) footer.
- **Two-panel auth** — the black brand panel + white form; parameterise the
  headline / stats / chips / badge.
- **Stepper** — for KYC.
- **Empty state** — icon, one line, one CTA.

# Production Readiness Pass — 2026-08-24

Scope: fix functional bugs, runtime errors/crashes, inconsistencies, loose ends,
and client-side errors found across the Django app. Security bugs are in scope
only when major/critical (financial/data-integrity impact); minor security
hardening is out of scope for this pass.

Audit method: `manage.py check` / `--deploy`, `py_compile` over all 424 first-party
`.py` files (0 syntax errors), `pyflakes` over the whole tree (433 findings
triaged), plus manual read-through of the request paths most likely to be hit in
production (core urls/views, Shopify integration, wallet/payment, admin dashboards).

Legend: [x] done · [ ] pending · [~] flagged only (not changed, needs a product
decision or is out of bounded-fix scope)

## Phase 1 — Core Django config (idiotship/)
- [x] `settings.py`: `MIDDLEWARE` had `CorsMiddleware` and `CommonMiddleware`
      each listed twice — deduped (double-running middleware on every request).
- [x] `settings.py`: `CORS_ALLOWED_ORIGINS` was defined twice; the second
      definition silently clobbered the first, dropping the local dev
      (`localhost:3000/5500`) and `dashboard.idiotship.tech` origins. Merged
      into a single list.
- [x] `urls.py`: dropped the pointless `from django.conf.urls import handler404,
      handler500` import that was immediately shadowed by the string
      assignments two lines down (pyflakes: redefinition of unused import).
- [x] `urls.py`: `bdl_integration` and `zippyy_integration` are both in
      `INSTALLED_APPS` and both ship a `urls.py` with a `webhook/` route, but
      neither was wired into the root urlconf — their courier status webhooks
      were unroutable (404) in production. Added both include() paths.
- [x] `views.py` `index()`: returned `None` (Django crash: "didn't return an
      HttpResponse") for any authenticated user whose `role` isn't exactly
      one of `user/admin/super_admin` — possible since `User.role` is
      `null=True`. Added a safe fallback redirect.

## Phase 2 — Shopify integration (shopify_integration/)
- [x] `models.py` `ShopifyStore.get_shopify_store_by_shop_url()` used `.get()`,
      which raises `DoesNotExist` for any unrecognized shop domain. Every
      caller treated the result as "returns `None` if not found"
      (`if store`/`if not store` checks). Any webhook/OAuth hit from an
      unregistered shop crashed with a 500. Changed to `.filter().first()`.
- [x] `views.py` `_handle_webhook`, `oauth_uninstall`, `webhook_orders`: each
      dereferenced `store.user` *before* checking `store` was truthy, which
      would still crash even after the fix above. Reordered to guard first.
- [x] `views.py` `fetch_orders`, `merchant_list`, `sync_orders`: queried
      `User.shopify_shop_domain` / `User.shopify_access_token` — fields that
      only exist on `ShopifyStore`, not `User` (confirmed via `account/models.py`).
      These three endpoints raised `FieldError`/`AttributeError` on every
      call — 100% broken. Rewrote all three against `ShopifyStore`.
      (This also fixes `_log_webhook(..., user.shopify_shop_domain, ...)`
      passing a plain string into a field that requires a `ShopifyStore`
      FK instance — would have raised `ValueError` on save.)
- [x] `utils/hmac.py` `verify_oauth_hmac`: computed the digest using
      `store.shopify_api_token` (the API key/client id) instead of
      `store.shopify_api_secret` (the client secret). Per Shopify's OAuth
      spec the secret is required — as written this check could never pass.
- [x] Re-enabled HMAC verification (user-approved) in `_handle_webhook`
      (webhook orders/create/updated/cancelled/paid) and `oauth_callback`
      (OAuth install). Previously commented out, meaning anyone could POST a
      forged "order cancelled" or "order paid" webhook and trigger real
      wallet refunds / shipment cancellations.
      **Action needed from you:** confirm `SHOPIFY_WEBHOOK_SECRET` (and each
      connected store's per-merchant `shopify_webhook_secret`, if used) is
      correctly set in the production `.env` — if it's blank or wrong, real
      Shopify webhooks will start getting rejected with 401 instead of being
      silently trusted. Same for `SHOPIFY_API_SECRET` used in OAuth.

## Phase 3 — Wallet / payments (wallet/)
- [x] `views.py` `callback` (PhonePe webhook, routed at `wallet:callback`):
      the entire body past the JSON parse was commented out, so the function
      fell off the end and returned `None` — a guaranteed 500 crash every
      time PhonePe hit this webhook. Actual wallet crediting happens
      server-side via `payment_redirect()`'s active `get_order_status()`
      call (verified against PhonePe's API, not client-supplied data), so
      this endpoint doesn't need to duplicate that logic — it now just
      returns `HttpResponse("OK")` so PhonePe stops seeing failures/retries.
- [x] `views.py` `payment_redirect`: `Transaction.objects.get(...)` for the
      merchant txn id had no error handling — a stale/replayed/bad redirect
      URL raised `DoesNotExist` (500). Wrapped with a friendly redirect.

## Phase 4 — Superadmin dashboard (superadmin_panel/)
- [x] `views.py` `dashboard_data` ("overview" and "clients" tabs, marked
      `# TODO: Implement real data fetching`): every stat
      (`total_pickup_order`, `total_in_transit_order`, `total_delivered_order`,
      `total_ndr_order`, `total_rto_order`, and the "clients" tab equivalents)
      ran the exact same copy-pasted `Count("total_amount")` aggregate with no
      status filter — every card on the dashboard showed an identical number.
      Rewrote to filter by the real `Order.status` values.
- [x] Same view: the `date_filter` (`this_month`/`last_month`/`this_year`)
      was read and validated but never applied to the queryset — selecting
      any range silently returned all-time totals. Now applied via
      `order_date`.
- [~] `edit_rate_card` view: POST handler is a literal `# TODO: complete`
      no-op (silently discards the submitted form, no error/success
      message). Left as-is — implementing real rate-card-edit semantics is a
      new feature (needs a spec for how `RateCard`'s JSON structure should
      be diffed/patched), not a bounded bug fix. Flagging for a follow-up.

## Phase 5 — Smaller cleanups
- [x] `smartship_integration/common.py` `track_shipment()`: removed a dead
      `global SESSION` statement (pyflakes: never assigned in this scope —
      leftover from a copy-pasted function, harmless but confusing).

## Phase 6 — Investigated, not changed (flagged for awareness)
- [~] 15 files use bare/broad `except:`/`except Exception as e: pass` blocks
      that swallow errors without logging (`account/views.py`,
      `order_manager/views.py`, `order_manager/validation.py`,
      `*_integration/common.py` for bdl/fship/jiffy/rapidshyp/rapidshyp_new,
      etc.). This is a widespread, deliberate-looking defensive style rather
      than a single fixable bug — rewriting all of it is a large, low-value
      diff. Recommend a follow-up pass focused specifically on courier-API
      error paths (that's where a swallowed exception costs the most —
      silent shipment failures).
- [~] `order_manager/tasks.py` `bulk_cancel_orders_by_courier_handler`
      computes a cancel response (`cancel_res`) but never returns it, so
      callers can't tell if the courier cancel actually succeeded — same
      "swallowed result" shape as above. Needs a product decision on what
      the caller should do with a failed cancel, so left as a flagged gap.
- [~] `dev/*.py` (`all_users_mis.py`, `cod_remitannce.py`,
      `debit_shipping_charges.py`, etc.): standalone one-off maintenance
      scripts, most reference `Order`/`OrderItem`/`Transaction`/`User`
      without importing them (pyflakes: undefined name) — they're not
      imported by the Django app itself (not in any app's code path), so
      they don't affect the running site. Left alone since fixing ~15
      scripts that are run manually, ad hoc, is outside "production ready
      app" scope — flag if you actually run these.
- [~] `theme/static/assets/js/label_client_pdf.js` (1485 lines) and
      `theme/static/assets/js/custom.js` are vendor/template-generated
      front-end code; skimmed for obvious breakage (none found in the parts
      reviewed) but not exhaustively line-reviewed given the size — flag if
      you're seeing a specific console error/crash there and I'll dig in.

## Phase 7 — Verification
- [x] `python -m py_compile` over all 424 first-party files: 0 errors (before
      and after changes).
- [x] `manage.py check`: 0 issues (before and after changes).
- [x] Re-ran `pyflakes` after edits to confirm no new warnings introduced by
      the fixes.

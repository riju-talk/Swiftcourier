/**
 * Client-side label PDF: pdfMake + JsBarcode + optional pdf-lib merge.
 *
 * Worker boundary: pure data helpers exposed on ShipzeeLabelPdfCore; anything using
 * document/canvas/JsBarcode/pdfMake must stay on the main thread until a worker
 * bundles those APIs (e.g. OffscreenCanvas + pdfMake in worker).
 */
(function () {
  var MM_TO_PT = 2.834645669;
  var SHIPZEE_POWERED_LOGO = "/static/images/logo/shipzee_logo.png";
  var LABELS_PER_PDF_CHUNK = 15;
  var DOC_BUILD_YIELD_EVERY = 8;
  var LOGO_BATCH_SIZE = 12;
  var AMAZON_MERGE_YIELD_EVERY = 3;

  var BARCODE_MEMORY = new Map();
  var LOGO_MEMORY = new Map();

  var DEV =
    !!(window.LABEL_PDF_DEV ||
      (typeof localStorage !== "undefined" && localStorage.getItem("shipzee_label_pdf_dev")));

  function timeStart(label) {
    if (DEV) console.time(label);
  }
  function timeEnd(label) {
    if (DEV) console.timeEnd(label);
  }

  /**
   * Cooperate with the event loop between heavy chunks. When the window is minimized or the tab is
   * in the background, requestAnimationFrame is throttled (~1/s), which makes large PDF jobs crawl;
   * MessageChannel schedules a normal task and keeps throughput much closer to foreground speed.
   */
  var _yieldPort1;
  var _yieldPort2;
  function raf() {
    return new Promise(function (resolve) {
      var hidden =
        typeof document !== "undefined" &&
        (document.hidden || document.visibilityState === "hidden");
      if (hidden) {
        if (!_yieldPort1) {
          var ch = new MessageChannel();
          _yieldPort1 = ch.port1;
          _yieldPort2 = ch.port2;
          _yieldPort1.onmessage = function () {
            var fn = _yieldPort1._szY;
            _yieldPort1._szY = null;
            if (fn) fn();
          };
        }
        _yieldPort1._szY = resolve;
        _yieldPort2.postMessage(null);
      } else {
        requestAnimationFrame(resolve);
      }
    });
  }

  function quickHash(s) {
    var h = 5381;
    for (var i = 0; i < s.length; i++) {
      h = ((h << 5) + h) ^ s.charCodeAt(i);
    }
    return (h >>> 0).toString(36);
  }

  function text(v) {
    return v == null ? "" : String(v);
  }

  /**
   * Single canonical page size for all label logic (API/boot typos, casing, hyphens).
   * Without this, caps/trim can fall through to 4x6 when value is not exactly "a4_single".
   */
  function normalizedLabelPageSize(settings) {
    var raw = (settings && settings.label_page_size) || "";
    raw = String(raw).trim().toLowerCase().replace(/-/g, "_");
    raw = raw.replace(/\s+/g, "");
    if (raw === "a4single") raw = "a4_single";
    if (raw === "a4" || raw === "a4_single" || raw === "4x6" || raw === "3x5") return raw;
    return "4x6";
  }

  /** Trim for table cells; keeps room for "...." suffix (4 chars). */
  function truncateLabelText(s, maxLen) {
    s = text(s);
    if (!maxLen || maxLen < 6) maxLen = 14;
    if (s.length <= maxLen) return s;
    return s.slice(0, maxLen - 4) + "...";
  }

  function labelPdfMaxProducts(settings) {
    var lp = normalizedLabelPageSize(settings);
    if (lp === "a4_single") return 14;
    if (lp === "a4") return 4;
    if (lp === "3x5") return 3;
    return 4;
  }

  function labelPdfMaxProductNameLen(settings) {
    var lp = normalizedLabelPageSize(settings);
    if (lp === "a4_single") return 48;
    if (lp === "a4") return 41;
    if (lp === "3x5") return 40;
    return 40;
  }

  function labelPdfMaxSkuLen() {
    return 30;
  }

  /** Vertical gaps between sections: full a4Single scale blows layout height; cap for a4_single. */
  function sectionVerticalScale(settings) {
    return normalizedLabelPageSize(settings) === "a4_single" ? 1.02 : a4SingleScale(settings);
  }

  function orderBarcodeRasterHeightPx(settings) {
    return normalizedLabelPageSize(settings) === "a4_single" ? 36 : Math.round(26 * a4SingleScale(settings));
  }

  function orderBarcodeFitBox(settings) {
    if (normalizedLabelPageSize(settings) === "a4_single") return [142, 32];
    var ims = a4SingleScale(settings);
    return [Math.round(92 * ims), Math.round(22 * ims)];
  }

  function awbBarcodeRasterHeightPx(settings) {
    var lp = normalizedLabelPageSize(settings);
    if (lp === "a4_single") return 32;
    if (lp === "3x5") return 32;
    return 34;
  }

  function awbBarcodeWidthPt(settings) {
    var lp = normalizedLabelPageSize(settings);
    if (lp === "3x5") return 108;
    if (lp === "a4_single") return 170;
    return 120;
  }

  /**
   * Merchant logo in header (~35% width column). Pt box for pdfMake fit — sized per page so it is neither tiny nor dominant.
   */
  function merchantHeaderLogoFit(settings) {
    var lp = normalizedLabelPageSize(settings);
    if (lp === "a4_single") return [108, 62];
    if (lp === "a4") return [66, 42];
    if (lp === "3x5") return [52, 34];
    return [76, 48];
  }

  /** "Powered by Idiotship" mark — smaller than merchant logo, scaled per format. */
  function shipzeeFooterLogoFit(settings) {
    var lp = normalizedLabelPageSize(settings);
    if (lp === "a4_single") return [58, 18];
    if (lp === "a4") return [42, 13];
    if (lp === "3x5") return [38, 12];
    return [46, 14];
  }

  function mmToPt(mm) {
    return mm * MM_TO_PT;
  }

  function inr(v) {
    return "₹" + text(v);
  }

  function inr2(v) {
    var n = Number(v);
    if (!isFinite(n)) return "₹" + "0.00";
    return "₹" + n.toFixed(2);
  }

  function inrSmart(v) {
    var n = Number(v);
    if (!isFinite(n)) return "₹" + text(v);
    var rounded = Math.round((n + Number.EPSILON) * 100) / 100;
    if (Math.abs(rounded - Math.round(rounded)) < 1e-9) return "₹" + String(Math.round(rounded));
    return "₹" + rounded.toFixed(2).replace(/\.?0+$/, "");
  }

  /** pdfMake has no CSS transform — scale rasters, barcode heights, and vertical gaps to fill A4. */
  var A4_SINGLE_LAYOUT_SCALE = 2.32;
  /** a4_single text: legacy bases were for 4×6; ×2.32 made 6pt→14pt and 12pt→28pt. Map with a mild slope + clamp so body vs title stays distinct without huge gaps. */
  var A4_SINGLE_FONT_CENTER_IN = 7.6;
  var A4_SINGLE_FONT_CENTER_OUT = 11;
  var A4_SINGLE_FONT_SLOPE = 0.5;
  var A4_SINGLE_FONT_MIN = 10;
  var A4_SINGLE_FONT_MAX = 13.5;

  function a4SingleScale(settings) {
    return normalizedLabelPageSize(settings) === "a4_single" ? A4_SINGLE_LAYOUT_SCALE : 1;
  }

  function fontSizeFor(settings, base) {
    var size = normalizedLabelPageSize(settings);
    if (size === "3x5") return Math.min(5, base - 1.6);
    if (size === "a4_single") {
      var t =
        A4_SINGLE_FONT_CENTER_OUT + (Number(base) - A4_SINGLE_FONT_CENTER_IN) * A4_SINGLE_FONT_SLOPE;
      if (t < A4_SINGLE_FONT_MIN) t = A4_SINGLE_FONT_MIN;
      if (t > A4_SINGLE_FONT_MAX) t = A4_SINGLE_FONT_MAX;
      return Math.round(t * 10) / 10;
    }
    return base;
  }

  function pageConfig(labelPageSize) {
    var lp = (labelPageSize || "4x6").toString().trim().toLowerCase().replace(/-/g, "_").replace(/\s+/g, "");
    if (lp === "a4single") lp = "a4_single";
    if (lp === "a4") {
      return { widthMm: 96, heightMm: 140, type: "a4" };
    }
    if (lp === "a4_single") {
      return { type: "a4_single" };
    }
    if (lp === "3x5") {
      return { widthMm: 76.2, heightMm: 127, type: "3x5" };
    }
    return { widthMm: 100, heightMm: 150, type: "4x6" };
  }

  /** Persistent + in-memory; key shape barcode_${value}_${height} (long values hashed). */
  function barcodeStorageKey(value, heightPx) {
    var v = text(value);
    var h = String(heightPx || 30);
    if (v.length > 120) {
      return "barcode_" + quickHash(v + "\0" + h) + "_" + h;
    }
    var safe = v.replace(/[\u0000-\u001f\\]/g, "_");
    return "barcode_" + safe + "_" + h;
  }

  /**
   * Lazy barcode: memory → localStorage → JsBarcode (PNG). Same code path as before for pdfMake images.
   */
  function getBarcode(value, heightPx) {
    var h = heightPx || 30;
    var memKey = text(value) + "|" + String(h);
    if (BARCODE_MEMORY.has(memKey)) return BARCODE_MEMORY.get(memKey);

    var storageKey = barcodeStorageKey(value, h);
    if (window.ShipzeePersistentCache) {
      var persisted = ShipzeePersistentCache.get(storageKey);
      if (persisted) {
        BARCODE_MEMORY.set(memKey, persisted);
        return persisted;
      }
    }

    if (typeof JsBarcode === "undefined") return "";

    var t0 = DEV && typeof performance !== "undefined" ? performance.now() : 0;
    var canvas = document.createElement("canvas");
    JsBarcode(canvas, text(value), {
      format: "CODE128",
      displayValue: false,
      margin: 0,
      width: 1.3,
      height: h,
    });
    var dataUrl = canvas.toDataURL("image/png");
    if (DEV && t0) {
      window.__labelPdfBarcodeMs = (window.__labelPdfBarcodeMs || 0) + (performance.now() - t0);
    }

    BARCODE_MEMORY.set(memKey, dataUrl);
    if (window.ShipzeePersistentCache) {
      try {
        ShipzeePersistentCache.set(storageKey, dataUrl);
      } catch (e) {}
    }
    return dataUrl;
  }

  /** Bump version when logo bytes / handling change so localStorage is not reused incorrectly. */
  function logoPersistentKey(url) {
    return "logo_v6_" + quickHash(text(url));
  }

  /**
   * Downscale raster logos for faster pdfMake embedding (display size set by merchantHeaderLogoFit / shipzeeFooterLogoFit).
   * Also fixes pdfMake/pdfkit grayscale+alpha PNG black matte by re-exporting RGBA PNG from canvas.
   * JPEG/WEBP without alpha → JPEG output; PNG/WEBP/GIF (transparency) → PNG output.
   */
  function downscaleRasterDataUrlForPdf(dataUrl, maxW, maxH) {
    return new Promise(function (resolve) {
      if (!dataUrl || dataUrl.indexOf("data:image/") !== 0) {
        resolve(dataUrl || "");
        return;
      }
      var mw = maxW > 0 ? maxW : 224;
      var mh = maxH > 0 ? maxH : 128;
      var usePngOut = /^data:image\/(png|webp|gif)/i.test(dataUrl);
      var img = new Image();
      img.onload = function () {
        try {
          var w = img.naturalWidth || img.width;
          var h = img.naturalHeight || img.height;
          if (!w || !h) {
            resolve(dataUrl);
            return;
          }
          var scale = Math.min(mw / w, mh / h, 1);
          var cw = Math.max(1, Math.round(w * scale));
          var ch = Math.max(1, Math.round(h * scale));
          var canvas = document.createElement("canvas");
          canvas.width = cw;
          canvas.height = ch;
          var ctx = canvas.getContext("2d");
          if (!ctx) {
            resolve(dataUrl);
            return;
          }
          ctx.clearRect(0, 0, cw, ch);
          ctx.drawImage(img, 0, 0, cw, ch);
          if (usePngOut) {
            resolve(canvas.toDataURL("image/png"));
          } else {
            resolve(canvas.toDataURL("image/jpeg", 0.82));
          }
        } catch (e) {
          resolve(dataUrl);
        }
      };
      img.onerror = function () {
        resolve(dataUrl);
      };
      img.src = dataUrl;
    });
  }

  async function logoData(url) {
    var key = text(url);
    if (!key) return "";
    if (LOGO_MEMORY.has(key)) return LOGO_MEMORY.get(key);

    var pkey = logoPersistentKey(key);
    if (window.ShipzeePersistentCache) {
      var cached = ShipzeePersistentCache.get(pkey);
      if (cached) {
        LOGO_MEMORY.set(key, cached);
        return cached;
      }
    }

    try {
      var res = await fetch(key, { credentials: "same-origin" });
      if (!res.ok) {
        LOGO_MEMORY.set(key, "");
        return "";
      }
      var data = "";
      if (window.ShipzeeImageOptimizer) {
        data = await ShipzeeImageOptimizer.optimizeFromResponse(res, 200, 120, 0.7);
      } else {
        data = await readBlobAsDataUrl(await res.blob());
      }
      if (!data) data = "";
      var isPowered = key === SHIPZEE_POWERED_LOGO;
      var maxW = isPowered ? 220 : 280;
      var maxH = isPowered ? 72 : 168;
      data = await downscaleRasterDataUrlForPdf(data, maxW, maxH);
      LOGO_MEMORY.set(key, data);
      if (window.ShipzeePersistentCache && data) {
        try {
          ShipzeePersistentCache.set(pkey, data);
        } catch (e) {}
      }
      return data;
    } catch (e) {
      LOGO_MEMORY.set(key, "");
      return "";
    }
  }

  function readBlobAsDataUrl(blob) {
    if (window.ShipzeeImageOptimizer && ShipzeeImageOptimizer.blobToDataUrl) {
      return ShipzeeImageOptimizer.blobToDataUrl(blob);
    }
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onloadend = function () {
        resolve(reader.result || "");
      };
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }

  /** Parallel logo loads in batches + rAF between batches to limit jank. */
  async function preloadLogosParallel(labels, settings) {
    timeStart("label_pdf_logo_load");
    var urls = [];
    var seen = new Set();
    var i;
    if (settings.show_logo) {
      for (i = 0; i < labels.length; i++) {
        var u = text(labels[i].logo_url);
        if (!u || seen.has(u)) continue;
        seen.add(u);
        urls.push(u);
        if (urls.length % 10 === 0) await raf();
      }
    }
    if (settings.show_powered_by && !seen.has(SHIPZEE_POWERED_LOGO)) {
      urls.push(SHIPZEE_POWERED_LOGO);
    }

    for (var b = 0; b < urls.length; b += LOGO_BATCH_SIZE) {
      var slice = urls.slice(b, b + LOGO_BATCH_SIZE);
      await Promise.all(
        slice.map(function (u) {
          return logoData(u);
        })
      );
      await raf();
    }
    timeEnd("label_pdf_logo_load");
  }

  /**
   * One label = one page: cap line items, truncate names, optional "...." row if more exist.
   * Order total row always uses label.total_amount (full order), not sum of visible lines.
   */
  function prepareLabelProductRows(label, settings) {
    var products = Array.isArray(label.products) ? label.products : [];
    if (!products.length) return [];

    var maxN = labelPdfMaxProducts(settings);
    var maxName = labelPdfMaxProductNameLen(settings);
    var maxSku = labelPdfMaxSkuLen();
    var rows = [];
    var i;
    for (i = 0; i < products.length && i < maxN; i++) {
      var p = products[i];
      rows.push({
        name: truncateLabelText(text(p.name), maxName),
        sku: truncateLabelText(text(p.sku), maxSku),
        hsn: truncateLabelText(text(p.hsn), 18),
        qty: p.qty,
        price: p.price,
        amount: p.amount,
      });
    }
    if (products.length > maxN) {
      rows.push({ _ellipsis: true, remainingCount: products.length - maxN });
    }
    return rows;
  }

  function splitProductChunks(label, settings) {
    return [prepareLabelProductRows(label, settings)];
  }

  var LAYOUT_NO_BORDERS = "noBorders";
  var PRODUCT_TABLE_LAYOUT = {
    hLineWidth: function () {
      return 0.6;
    },
    vLineWidth: function () {
      return 0;
    },
    hLineColor: function () {
      return "#c9c9c9";
    },
    paddingLeft: function () {
      return 2;
    },
    paddingRight: function () {
      return 2;
    },
    paddingTop: function () {
      return 2;
    },
    paddingBottom: function () {
      return 2;
    },
  };

  function productTableLayoutFor(settings) {
    if (normalizedLabelPageSize(settings) !== "a4_single") return PRODUCT_TABLE_LAYOUT;
    return {
      hLineWidth: function () {
        return 0.6;
      },
      vLineWidth: function () {
        return 0;
      },
      hLineColor: function () {
        return "#c9c9c9";
      },
      paddingLeft: function () {
        return 3;
      },
      paddingRight: function () {
        return 3;
      },
      paddingTop: function () {
        return 1;
      },
      paddingBottom: function () {
        return 1;
      },
    };
  }

  /** Wider Item/SKU for a4_single so noWrap cells do not draw into each other. */
  function productTableWidths(settings, showItemColumn) {
    var lp = normalizedLabelPageSize(settings);
    var a4s = lp === "a4_single";
    var is3x5 = lp === "3x5";
    var disc = !!settings.show_discount;
    if (a4s) {
      if (disc && showItemColumn) return ["34%", "20%", "7%", "9%", "9%", "7%", "14%"];
      if (disc && !showItemColumn) return ["0%", "36%", "10%", "14%", "13%", "9%", "18%"];
      /* No discount: still need a real width for Total; prior rows summed to 100% with "0%" last — breaks layout. */
      if (!disc && showItemColumn) return ["32%", "20%", "8%", "10%", "13%", "17%"];
      return ["0%", "36%", "11%", "15%", "14%", "24%"];
    }
    /* 3×5 page is narrow; 10% Total column forced ₹ amounts to wrap (e.g. ₹1000). */
    if (is3x5) {
      if (disc && showItemColumn) return ["21%", "18%", "8%", "12%", "13%", "8%", "20%"];
      if (disc && !showItemColumn) return ["0%", "26%", "11%", "16%", "17%", "9%", "21%"];
      if (!disc && showItemColumn) return ["25%", "19%", "8%", "13%", "15%", "20%"];
      return ["0%", "28%", "12%", "17%", "21%", "22%"];
    }
    if (disc) {
      return showItemColumn
        ? ["24%", "21%", "9%", "13%", "14%", "9%", "10%"]
        : ["0%", "29%", "12%", "18%", "19%", "10%", "12%"];
    }
    return showItemColumn
      ? ["28%", "22%", "9%", "14%", "17%", "10%"]
      : ["0%", "32%", "13%", "19%", "26%", "10%"];
  }

  /** Body label uses large scale; product table needs a cap or columns collide with noWrap. */
  function productTableBodyFontSize(settings) {
    var raw = fontSizeFor(settings, 5);
    if (normalizedLabelPageSize(settings) === "a4_single") return Math.min(raw, 11.3);
    return raw;
  }

  var LABEL_CELL_BORDER_LINES = {
    hLineColor: function () {
      return "#8c8c8c";
    },
    vLineColor: function () {
      return "#8c8c8c";
    },
    hLineWidth: function () {
      return 1;
    },
    vLineWidth: function () {
      return 1;
    },
  };

  /** "For queries: Mob … | Email: …" from settings; falls back to parsing legacy label.support_info. */
  function supportQueriesLine(settings, label) {
    var mob = text(settings.support_phone).trim();
    var em = text(settings.support_email).trim();
    if (!mob && !em && label && label.support_info) {
      var raw = text(label.support_info).trim();
      var sep = raw.indexOf(" | ");
      if (sep >= 0) {
        mob = raw.slice(0, sep).trim();
        em = raw.slice(sep + 3).trim();
      } else {
        mob = raw;
      }
    }
    var parts = [];
    if (mob) parts.push("Mob: " + mob);
    if (em) parts.push("Email: " + em);
    if (!parts.length) return "";
    return "For queries: " + parts.join(" | ");
  }

  function sectionContainer(content, options, settings) {
    var opts = options || {};
    var s = sectionVerticalScale(settings);
    return {
      margin: [0, (opts.marginTop || 0) * s, 0, (opts.marginBottom || 0) * s],
      table: { widths: ["*"], body: [[content]] },
      layout: LAYOUT_NO_BORDERS,
    };
  }

  function productTableNode(label, settings, productRows, showTotal) {
    var lp = normalizedLabelPageSize(settings);
    var a4s = lp === "a4_single";
    var is3x5 = lp === "3x5";
    var nowrap = a4s ? { noWrap: true } : {};
    var showItemColumn = !!settings.show_product;
    var widths = productTableWidths(settings, showItemColumn);
    var colCount = widths.length;
    var header = [{ text: showItemColumn ? "Item" : "", bold: true, alignment: "left" }];
    header = header.concat([
      { text: "SKU", bold: true, alignment: "left" },
      { text: "HSN", bold: true, alignment: "left" },
      { text: "Qty", bold: true, alignment: "center" },
      { text: "Rate", bold: true, alignment: "right" },
    ]);
    if (settings.show_discount) header.push({ text: "Disc", bold: true, alignment: "right" });
    header.push({ text: "Total", bold: true, alignment: "right" });

    var body = [header];
    var i;
    for (i = 0; i < productRows.length; i++) {
      var p = productRows[i];
      if (p && p._ellipsis) {
        var moreN = Math.max(0, Math.floor(Number(p.remainingCount) || 0));
        var moreLabel =
          moreN === 1 ? "... + 1 product" : "... + " + moreN + " products";
        if (!moreN) moreLabel = "... + more products";
        var er = [{ text: moreLabel, colSpan: colCount, alignment: "center", italics: true, color: "#555555" }];
        var ej;
        for (ej = 1; ej < colCount; ej++) er.push({});
        body.push(er);
        continue;
      }
      var row = [
        Object.assign({ text: showItemColumn ? text(p.name) : "", alignment: "left" }, nowrap),
        Object.assign({ text: text(p.sku), alignment: "left" }, nowrap),
        Object.assign({ text: text(p.hsn), alignment: "left" }, nowrap),
        Object.assign({ text: text(p.qty), alignment: "center" }, nowrap),
        Object.assign({ text: inrSmart(p.price), alignment: "right" }, nowrap),
      ];
      if (settings.show_discount) row.push(Object.assign({ text: inrSmart(label.discount), alignment: "right" }, nowrap));
      row.push(Object.assign({ text: inrSmart(p.amount), alignment: "right" }, nowrap));
      body.push(row);
    }

    if (showTotal && settings.show_total_amount) {
      var totalRow = [{ text: "Total : " + inrSmart(label.total_amount), colSpan: colCount, alignment: "right", bold: true }];
      if (is3x5) Object.assign(totalRow[0], { noWrap: true });
      for (var j = 1; j < colCount; j++) totalRow.push({});
      body.push(totalRow);
    }

    return sectionContainer(
      {
        width: "100%",
        table: { headerRows: 1, widths: widths, body: body, dontBreakRows: true },
        layout: productTableLayoutFor(settings),
        fontSize: productTableBodyFontSize(settings),
      },
      { marginTop: a4s ? 2 : 5 },
      settings
    );
  }

  function footerNodes(label, settings, showTotal) {
    if (!showTotal) return [];
    var nodes = [];
    var a4s = normalizedLabelPageSize(settings) === "a4_single";
    if (settings.show_pickup_address) {
      var hubFull =
        text(label.hub_name) +
        ", " +
        text(label.hub_line1) +
        ", " +
        text(label.hub_city) +
        ", " +
        text(label.hub_state) +
        ", " +
        text(label.hub_country) +
        " - " +
        text(label.hub_pincode) +
        ", Mob: " +
        text(label.hub_phone);
      if (a4s) hubFull = truncateLabelText(hubFull, 96);
      nodes.push(
        sectionContainer(
          {
            width: "100%",
            stack: [
              { text: "Pickup and Return Address:", bold: true, fontSize: fontSizeFor(settings, 8) },
              {
                text: hubFull,
                fontSize: fontSizeFor(settings, 7.5),
                margin: [0, a4s ? 0.5 : 1, 0, 0],
                noWrap: a4s,
              },
            ],
          },
          { marginTop: a4s ? 2 : 5 },
          settings
        )
      );
    }

    var footerStack = [];
    if (settings.show_support_info) {
      var sup = supportQueriesLine(settings, label);
      if (sup) {
        if (a4s) sup = truncateLabelText(sup, 96);
        footerStack.push({
          text: sup,
          alignment: "left",
          margin: [0, 0, 0, 0],
          fontSize: fontSizeFor(settings, a4s ? 6.6 : 7),
          noWrap: a4s,
        });
      }
    }
    footerStack.push({
      text: "This is computer generated document, hence does not required signature.",
      italics: true,
      alignment: "left",
      margin: [0, a4s ? 0.5 : 0, 0, 0],
      fontSize: fontSizeFor(settings, a4s ? 6.4 : 7),
      noWrap: a4s,
    });
    if (settings.show_powered_by) {
      var shipzeeLogo = LOGO_MEMORY.get(SHIPZEE_POWERED_LOGO) || "";
      var szFit = shipzeeFooterLogoFit(settings);
      if (a4s) {
        footerStack.push({
          margin: [0, 1, 0, 0],
          columnGap: 6,
          columns: [
            {
              width: "*",
              text: "Powered By Idiotship",
              bold: true,
              alignment: "left",
              fontSize: fontSizeFor(settings, 7),
              margin: [0, 1, 0, 0],
            },
            shipzeeLogo
              ? {
                  width: "auto",
                  image: shipzeeLogo,
                  fit: [szFit[0], szFit[1]],
                  alignment: "right",
                  margin: [0, 0, 0, 0],
                }
              : { width: "auto", text: "" },
          ],
        });
      } else {
        footerStack.push({
          margin: [0, 2, 0, 0],
          table: {
            widths: ["*", Math.max(44, szFit[0] + 8)],
            body: [
              [
                { text: "Powered By Idiotship", bold: true, alignment: "left", margin: [0, 4, 0, 0] },
                shipzeeLogo
                  ? { image: shipzeeLogo, fit: [szFit[0], szFit[1]], alignment: "right" }
                  : { text: "" },
              ],
            ],
          },
          layout: LAYOUT_NO_BORDERS,
        });
      }
    }
    nodes.push(
      sectionContainer(
        { width: "100%", stack: footerStack, alignment: "left", fontSize: fontSizeFor(settings, a4s ? 6.5 : 7) },
        { marginTop: a4s ? 1 : 3 },
        settings
      )
    );
    return nodes;
  }

  function firstPageHeaderSection(label, settings, logoImage) {
    var logoFit = merchantHeaderLogoFit(settings);
    var a4s = normalizedLabelPageSize(settings) === "a4_single";
    var addrBody = a4s ? 8.4 : 7.8;
    var addrLabel = a4s ? 9 : 7.8;
    var addrName = a4s ? 11 : 10.5;
    var addressLine = text(label.line1) + (label.line2 ? ", " + text(label.line2) : "");
    var rightAddressStack = [
      { text: "Deliver To:", fontSize: fontSizeFor(settings, addrLabel), alignment: "right" },
      {
        text: text(label.customer_name),
        bold: true,
        fontSize: fontSizeFor(settings, addrName),
        alignment: "right",
        margin: [0, 1, 0, 1],
      },
    ];
    if (text(label.company_name).trim()) {
      rightAddressStack.push({
        text: text(label.company_name),
        fontSize: fontSizeFor(settings, addrBody),
        alignment: "right",
        margin: [0, 0, 0, 1],
      });
    }
    rightAddressStack = rightAddressStack.concat([
      { text: addressLine, fontSize: fontSizeFor(settings, addrBody), alignment: "right" },
      {
        text: text(label.city) + ", " + text(label.state) + ", " + text(label.country),
        fontSize: fontSizeFor(settings, addrBody),
        alignment: "right",
      },
      { text: text(label.pincode), fontSize: fontSizeFor(settings, addrBody), alignment: "right" },
    ]);
    if (settings.show_customer_mobile) {
      rightAddressStack.push({
        text: "MOBILE NO: " + text(label.customer_phone),
        fontSize: fontSizeFor(settings, addrBody),
        alignment: "right",
        margin: [0, 1, 0, 0],
      });
    }

    return sectionContainer(
      {
        width: "100%",
        table: {
          widths: ["35%", "65%"],
          body: [
            [
              {
                stack:
                  settings.show_logo && logoImage
                    ? [{ image: logoImage, fit: [logoFit[0], logoFit[1]], alignment: "left" }]
                    : [{ text: "" }],
              },
              { stack: rightAddressStack, alignment: "right" },
            ],
          ],
        },
        layout: LAYOUT_NO_BORDERS,
      },
      { marginTop: 0 },
      settings
    );
  }

  function orderShippingSection(label, settings) {
    var gap = sectionVerticalScale(settings);
    var a4s = normalizedLabelPageSize(settings) === "a4_single";
    var secHead = a4s ? 10.2 : 9.5;
    var secBody = a4s ? 8.4 : 7.8;
    var orderBarcode = getBarcode(label.order_number || label.awb, orderBarcodeRasterHeightPx(settings));
    var obFit = orderBarcodeFitBox(settings);
    var shippingMeta = [
      { text: "Courier Name: " + text(label.courier), margin: [0, 0, 0, 1 * gap] },
    ];
    if (settings.show_weight) shippingMeta.push({ text: "Weight: " + text(label.weight) + " KG", margin: [0, 0, 0, 1 * gap] });
    if (settings.show_dimension) {
      shippingMeta.push({
        text: "Dimensions (cm): " + [text(label.length), text(label.width), text(label.height)].join(" X "),
        margin: [0, 0, 0, 0],
      });
    }

    return sectionContainer(
      {
        width: "100%",
        table: {
          widths: ["50%", "50%"],
          body: [
            [
              {
                stack: [
                  { text: "Order Info", bold: true, fontSize: fontSizeFor(settings, secHead), margin: [0, 0, 0, 2 * gap] },
                  { text: "Order Date: " + text(label.order_date), fontSize: fontSizeFor(settings, secBody), margin: [0, 0, 0, 1 * gap] },
                  {
                    text: "Order No: " + text(label.order_number),
                    bold: true,
                    fontSize: fontSizeFor(settings, secBody),
                    margin: [0, 0, 0, 3 * gap],
                  },
                  { image: orderBarcode, fit: obFit, alignment: "center" },
                ],
              },
              {
                stack: [{ text: "Shipping Info", bold: true, fontSize: fontSizeFor(settings, secHead), margin: [0, 0, 0, 2 * gap], alignment: "right" }].concat(
                  shippingMeta.map(function (line) {
                    return { text: line.text, margin: line.margin, alignment: "right", fontSize: fontSizeFor(settings, secBody) };
                  })
                ),
                alignment: "right",
              },
            ],
          ],
        },
        layout: LAYOUT_NO_BORDERS,
      },
      { marginTop: 5 },
      settings
    );
  }

  function codSection(label, settings) {
    var gap = sectionVerticalScale(settings);
    var a4s = normalizedLabelPageSize(settings) === "a4_single";
    var codHead = a4s ? 12.5 : 12;
    var codSub = a4s ? 8.7 : 8;
    var paymentMode = text(label.payment_mode).trim().toUpperCase();
    var isCod = paymentMode === "COD";
    var isPrepaid = !isCod;
    var awbBarcode = getBarcode(label.awb, awbBarcodeRasterHeightPx(settings));
    var awbW = awbBarcodeWidthPt(settings);
    var prepaidTopOffset = Math.round(fontSizeFor(settings, 8.5) * 1.2 + 2 * gap);
    var prepaidBlockHeight = Math.max(awbBarcodeRasterHeightPx(settings), 26);
    var leftPaymentColumn = isPrepaid
      ? {
          width: "40%",
          margin: [0, prepaidTopOffset, 0, 0],
          table: {
            widths: ["*"],
            heights: [prepaidBlockHeight],
            body: [
              [
                {
                  text: "Prepaid",
                  bold: true,
                  fontSize: fontSizeFor(settings, codHead),
                  alignment: "center",
                  valign: "middle",
                },
              ],
            ],
          },
          layout: LAYOUT_NO_BORDERS,
        }
      : [
          { text: "COD", bold: true, fontSize: fontSizeFor(settings, codHead), alignment: "center" },
          { text: "Collectable", bold: true, fontSize: fontSizeFor(settings, codSub), alignment: "center", margin: [0, 1, 0, 0] },
          {
            text: "Amt: " + inrSmart(label.total_amount),
            bold: true,
            fontSize: fontSizeFor(settings, codSub),
            alignment: "center",
            margin: [0, 1, 0, 0],
          }
        ];
    return sectionContainer(
      {
        width: "100%",
        columns: [
          isPrepaid ? leftPaymentColumn : { width: "40%", stack: leftPaymentColumn },
          {
            width: "60%",
            stack: [
              { text: "AWB No : " + text(label.awb), bold: true, alignment: "right", fontSize: fontSizeFor(settings, 8.5), margin: [0, 0, 0, 2 * gap] },
              {
                image: awbBarcode,
                width: awbW,
                alignment: "right",
              },
            ],
            alignment: "right",
          },
        ],
        layout: LAYOUT_NO_BORDERS,
      },
      { marginTop: 5 },
      settings
    );
  }

  function buildLabelDocDefinition(labelData) {
    var label = labelData.label || {};
    var settings = labelData.settings || {};
    var productRows = labelData.productRows || [];
    var showTotal = !!labelData.showTotal;
    var pageType = labelData.pageType || "first";
    var logoImage = LOGO_MEMORY.get(text(label.logo_url)) || "";

    var stack = [];
    if (pageType === "first") {
      stack.push(firstPageHeaderSection(label, settings, logoImage));
      stack.push(orderShippingSection(label, settings));
      stack.push(codSection(label, settings));
    }

    var pNode = productTableNode(label, settings, productRows, showTotal);
    if (pNode) stack.push(pNode);
    stack = stack.concat(footerNodes(label, settings, showTotal));
    return { stack: stack, unbreakable: true };
  }

  function chunkArray(arr, size) {
    var out = [];
    for (var i = 0; i < arr.length; i += size) {
      out.push(arr.slice(i, i + size));
    }
    return out;
  }

  /**
   * A4 grid is 2×2 (4 labels per sheet). Chunking with a non-multiple of 4 makes the last page of
   * each PDFLib-merged part show only 3 labels + an empty cell, then the next part starts fresh.
   */
  function labelsChunkSizeForPdfMerge(settings) {
    var lp = normalizedLabelPageSize(settings);
    if (lp !== "a4") return LABELS_PER_PDF_CHUNK;
    var n = Math.floor(LABELS_PER_PDF_CHUNK / 4) * 4;
    return n >= 4 ? n : 4;
  }

  async function buildPdfDefinitionAsync(labels, settings, pageCfg) {
    var lp = normalizedLabelPageSize(settings);
    var isA4Grid = lp === "a4";
    var isA4Single = lp === "a4_single";
    var pages = [];
    var iter = 0;
    var idx;
    for (idx = 0; idx < labels.length; idx++) {
      var label = labels[idx];
      var productRows = prepareLabelProductRows(label, settings);
      pages.push(
        buildLabelDocDefinition({
          label: label,
          settings: settings,
          productRows: productRows,
          showTotal: true,
          pageType: "first",
        })
      );
      iter++;
      if (iter % DOC_BUILD_YIELD_EVERY === 0) {
        await raf();
      }
    }
    if (isA4Grid) return buildA4GridDocument(pages, pageCfg);
    if (isA4Single) return buildA4SinglePageDocument(pages);
    return buildSingleLabelDocument(pages, pageCfg);
  }

  async function createPdfBytes(docDefinition) {
    return new Promise(function (resolve, reject) {
      try {
        pdfMake.createPdf(docDefinition).getBuffer(function (buffer) {
          var uint8 = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
          var arrBuffer = uint8.buffer.slice(uint8.byteOffset, uint8.byteOffset + uint8.byteLength);
          resolve(arrBuffer);
        });
      } catch (e) {
        reject(e);
      }
    });
  }

  function buildLabelCell(pageNode, labelW, labelH, cellOpts) {
    var co = cellOpts || {};
    var inset = co.compact ? [3, 2, 3, 3] : [5, 5, 5, 5];
    var pad = co.compact ? 2 : 3;
    var layout = Object.assign({}, LABEL_CELL_BORDER_LINES);
    layout.paddingLeft = function () {
      return pad;
    };
    layout.paddingRight = function () {
      return pad;
    };
    layout.paddingTop = function () {
      return pad;
    };
    layout.paddingBottom = function () {
      return pad;
    };
    var cell = { margin: inset, stack: pageNode.stack };
    if (co.valign) cell.valign = co.valign;
    return {
      table: {
        widths: [labelW],
        heights: [labelH],
        body: [[cell]],
      },
      layout: layout,
    };
  }

  var A4_GRID_OUTER_LAYOUT = {
    hLineWidth: function () {
      return 0;
    },
    vLineWidth: function () {
      return 0;
    },
    paddingLeft: function () {
      return 0;
    },
    paddingRight: function () {
      return 0;
    },
    paddingTop: function () {
      return 0;
    },
    paddingBottom: function () {
      return 0;
    },
  };

  function buildSingleLabelDocument(pages, pageCfg) {
    var exact3x5 = pageCfg.type === "3x5";
    /* Only 4×6 and 3×5 use this path — center label in page; flex * rows/cols balance slack so borders are not pushed to one corner. */
    var pageSize = exact3x5 ? { width: 216, height: 360 } : { width: mmToPt(pageCfg.widthMm), height: mmToPt(pageCfg.heightMm) };
    var baseInset = (exact3x5 ? 4 : 5) + 3;
    /* Tighter top/left to page edge; same total margin so box size unchanged (shift content up-left). */
    var tuckTL = 3;
    var mL = Math.max(1, baseInset - tuckTL);
    var mT = Math.max(1, baseInset - tuckTL);
    var mR = baseInset + tuckTL;
    var mB = baseInset + tuckTL;
    var boxW = pageSize.width - mL - mR;
    var boxH = pageSize.height - mT - mB;
    /* Shrink label box slightly so 1pt outer stroke stays inside the middle cell; * gutters split remainder evenly (true center). */
    var strokePad = 4;
    var labelW = Math.max(boxW - strokePad, 80);
    var labelH = Math.max(boxH - strokePad, 120);
    var content = [];
    var i;
    for (i = 0; i < pages.length; i++) {
      var node = {
        margin: [mL, mT, mR, mB],
        table: {
          widths: ["*", labelW, "*"],
          heights: ["*", labelH, "*"],
          body: [
            [{ text: "" }, { text: "" }, { text: "" }],
            [{ text: "" }, buildLabelCell(pages[i], labelW, labelH), { text: "" }],
            [{ text: "" }, { text: "" }, { text: "" }],
          ],
        },
        layout: A4_GRID_OUTER_LAYOUT,
      };
      if (i < pages.length - 1) node.pageBreak = "after";
      content.push(node);
    }

    return {
      pageSize: pageSize,
      pageMargins: [0, 0, 0, 0],
      content: content,
      defaultStyle: { fontSize: exact3x5 ? 7.1 : 8, lineHeight: exact3x5 ? 1.0 : 1.05 },
    };
  }

  function buildA4GridDocument(pages, pageCfg) {
    var a4Width = mmToPt(210);
    var a4Height = mmToPt(297);
    var marginL = mmToPt(10);
    var marginT = mmToPt(4);
    var marginR = mmToPt(10);
    var marginB = mmToPt(10);
    var colGap = mmToPt(3);
    var rowGap = mmToPt(3);
    var usableW = a4Width - marginL - marginR;
    var usableH = a4Height - marginT - marginB;
    var labelW = (usableW - colGap) / 2;
    var labelH = (usableH - rowGap) / 2;
    var rowsPerPage = 2;
    var perPage = 4;
    var content = [];
    var compactCell = { compact: true };

    var i;
    for (i = 0; i < pages.length; i += perPage) {
      var pageItems = pages.slice(i, i + perPage);
      var body = [];
      var r;
      for (r = 0; r < rowsPerPage; r++) {
        var left = pageItems[r * 2];
        var right = pageItems[r * 2 + 1];
        body.push([
          left ? buildLabelCell(left, labelW, labelH, compactCell) : { text: "" },
          { text: "" },
          right ? buildLabelCell(right, labelW, labelH, compactCell) : { text: "" },
        ]);
        if (r < rowsPerPage - 1) body.push([{ text: "" }, { text: "" }, { text: "" }]);
      }

      content.push({
        margin: [marginL, marginT, marginR, marginB],
        table: {
          widths: [labelW, colGap, labelW],
          heights: [labelH, rowGap, labelH],
          body: body,
        },
        layout: A4_GRID_OUTER_LAYOUT,
        pageBreak: i + perPage < pages.length ? "after" : undefined,
      });
    }

    return {
      pageSize: "A4",
      pageMargins: [0, 0, 0, 0],
      content: content,
      defaultStyle: { fontSize: 7.75, lineHeight: 1.02 },
    };
  }

  function buildA4SinglePageDocument(pages) {
    var margin = mmToPt(10);
    var labelW = mmToPt(210) - 2 * margin;
    var labelH = mmToPt(297) - 2 * margin;
    var content = [];
    var i;
    for (i = 0; i < pages.length; i++) {
      content.push({
        margin: [margin, margin, margin, margin],
        stack: [buildLabelCell(pages[i], labelW, labelH, { valign: "middle" })],
        pageBreak: i < pages.length - 1 ? "after" : undefined,
      });
    }
    return {
      pageSize: "A4",
      pageMargins: [0, 0, 0, 0],
      content: content,
      defaultStyle: { fontSize: 11, lineHeight: 1.08 },
    };
  }

  async function renderLabelsToPdfBytes(labels, settings, pageCfg) {
    settings = Object.assign({}, settings, { label_page_size: normalizedLabelPageSize(settings) });
    var batches = chunkArray(labels, labelsChunkSizeForPdfMerge(settings));
    if (batches.length === 1 || !window.PDFLib) {
      timeStart("label_pdf_pdfmake_render");
      var defOne = await buildPdfDefinitionAsync(labels, settings, pageCfg);
      var bytesOne = await createPdfBytes(defOne);
      timeEnd("label_pdf_pdfmake_render");
      return bytesOne;
    }

    timeStart("label_pdf_pdfmake_chunked");
    var merged = await PDFLib.PDFDocument.create();
    var bi;
    for (bi = 0; bi < batches.length; bi++) {
      var def = await buildPdfDefinitionAsync(batches[bi], settings, pageCfg);
      var partBytes = await createPdfBytes(def);
      var doc = await PDFLib.PDFDocument.load(partBytes);
      var copied = await merged.copyPages(doc, doc.getPageIndices());
      copied.forEach(function (p) {
        merged.addPage(p);
      });
      await raf();
    }
    var saved = await merged.save();
    timeEnd("label_pdf_pdfmake_chunked");
    return saved;
  }

  async function mergeAmazon(clientPdfBytes, labels, atsProxyUrl) {
    function hasPdfBytes(bytes) {
      if (!bytes) return false;
      if (typeof bytes.byteLength === "number") return bytes.byteLength > 0;
      if (typeof bytes.length === "number") return bytes.length > 0;
      return false;
    }

    var atsUrls = [];
    var i;
    for (i = 0; i < labels.length; i++) {
      var l = labels[i];
      if (!l.is_amazon) continue;
      if (l.amazon_label_url) atsUrls.push(l.amazon_label_url);
    }
    if (!atsUrls.length) return clientPdfBytes;
    if (!window.PDFLib) return clientPdfBytes;

    timeStart("label_pdf_amazon_merge");
    var pdf = await PDFLib.PDFDocument.create();
    var localPageCount = 0;
    if (hasPdfBytes(clientPdfBytes)) {
      var localDoc = await PDFLib.PDFDocument.load(clientPdfBytes);
      var localPages = await pdf.copyPages(localDoc, localDoc.getPageIndices());
      localPages.forEach(function (p) {
        pdf.addPage(p);
      });
      localPageCount = localPages.length;
    }

    var loadedDocsFromProxy = await Promise.all(
      atsUrls.map(function (url) {
        var fetchUrl = atsProxyUrl
          ? atsProxyUrl + "?url=" + encodeURIComponent(url)
          : url;
        return fetch(fetchUrl)
          .then(function (res) {
            if (!res.ok) throw new Error("HTTP " + res.status);
            return res.arrayBuffer();
          })
          .then(function (bytes) {
            return PDFLib.PDFDocument.load(bytes);
          })
          .catch(function (e) {
            console.error("Amazon label merge proxy/url fetch error", fetchUrl, e);
            return null;
          });
      })
    );

    var loadedDocs = loadedDocsFromProxy;

    var j;
    var atsPageCount = 0;
    for (j = 0; j < loadedDocs.length; j++) {
      var ext = loadedDocs[j];
      if (!ext) continue;
      var amzPages = await pdf.copyPages(ext, ext.getPageIndices());
      amzPages.forEach(function (p) {
        pdf.addPage(p);
      });
      atsPageCount += amzPages.length;
      if ((j + 1) % AMAZON_MERGE_YIELD_EVERY === 0) await raf();
    }

    var out = await pdf.save();
    timeEnd("label_pdf_amazon_merge");
    return out;
  }

  var LABEL_DOWNLOAD_OVERLAY_ID = "idiotship-label-download-overlay";

  /** In-page only — avoids opening another tab during generation (background throttling kills speed). */
  function showLabelDownloadOverlay() {
    if (typeof document === "undefined" || !document.body) return;
    if (document.getElementById(LABEL_DOWNLOAD_OVERLAY_ID)) return;
    var el = document.createElement("div");
    el.id = LABEL_DOWNLOAD_OVERLAY_ID;
    el.setAttribute("role", "status");
    el.setAttribute("aria-live", "polite");
    el.innerHTML =
      "<style>" +
      "@keyframes shipzee_label_dl_spin{to{transform:rotate(360deg)}}" +
      "#idiotship-label-download-overlay{position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;" +
      "font-family:system-ui,-apple-system,sans-serif;background:rgba(15,23,42,0.45)}" +
      "body.dark #idiotship-label-download-overlay,html.dark #idiotship-label-download-overlay{background:rgba(2,6,23,0.72)}" +
      "#idiotship-label-download-overlay .idiotship-label-dl-card{background:#fff;color:#18181b;padding:1.75rem 2rem;border-radius:12px;max-width:26rem;margin:1rem;" +
      "box-shadow:0 25px 50px -12px rgba(0,0,0,0.35);text-align:center;line-height:1.5;border:1px solid transparent}" +
      "body.dark #idiotship-label-download-overlay .idiotship-label-dl-card,html.dark #idiotship-label-download-overlay .idiotship-label-dl-card{" +
      "background:#0e1726;color:#e2e8f0;border-color:rgba(148,163,184,0.18);" +
      "box-shadow:0 25px 50px -12px rgba(0,0,0,0.55)}" +
      "#idiotship-label-download-overlay .idiotship-label-dl-title{margin:0 0 0.75rem;font-weight:600;font-size:1.05rem}" +
      "#idiotship-label-download-overlay .idiotship-label-dl-sub{margin:0;font-size:0.9rem;opacity:0.85;color:inherit}" +
      "body.dark #idiotship-label-download-overlay .idiotship-label-dl-sub,html.dark #idiotship-label-download-overlay .idiotship-label-dl-sub{" +
      "opacity:1;color:#94a3b8}" +
      "#idiotship-label-download-overlay .idiotship-label-dl-spin{box-sizing:border-box;width:44px;height:44px;margin:0 auto 1.1rem;" +
      "border:3px solid #e5e7eb;border-top-color:#4361ee;border-radius:50%;animation:shipzee_label_dl_spin .7s linear infinite}" +
      "body.dark #idiotship-label-download-overlay .idiotship-label-dl-spin,html.dark #idiotship-label-download-overlay .idiotship-label-dl-spin{" +
      "border-color:#334155;border-top-color:#4361ee}" +
      "@media (prefers-reduced-motion:reduce){" +
      "#idiotship-label-download-overlay .idiotship-label-dl-spin{animation:none!important;" +
      "border-color:#4361ee #e5e7eb #e5e7eb #e5e7eb!important}" +
      "body.dark #idiotship-label-download-overlay .idiotship-label-dl-spin,html.dark #idiotship-label-download-overlay .idiotship-label-dl-spin{" +
      "border-color:#4361ee #334155 #334155 #334155!important}}" +
      "</style>" +
      '<div class="idiotship-label-dl-card">' +
      '<div class="idiotship-label-dl-spin" aria-hidden="true"></div>' +
      '<p class="idiotship-label-dl-title">Preparing your labels…</p>' +
      '<p class="idiotship-label-dl-sub">Please wait. Very large batches can take several minutes.</p>' +
      "</div>";
    document.body.appendChild(el);
  }

  function hideLabelDownloadOverlay() {
    var el =
      typeof document !== "undefined" && document.getElementById
        ? document.getElementById(LABEL_DOWNLOAD_OVERLAY_ID)
        : null;
    if (el) el.remove();
  }

  function triggerPdfBlobDownloadInCurrentTab(blob) {
    var blobUrl = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = blobUrl;
    a.download = "labels_" + Date.now() + ".pdf";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () {
      URL.revokeObjectURL(blobUrl);
    }, 60000);
  }

  async function generateLabelsFromOrderIds(orderIds, apiUrl) {
    if (!orderIds || !orderIds.length) {
      alert("Please select at least one order.");
      return;
    }

    showLabelDownloadOverlay();
    timeStart("label_pdf_total");
    try {
      var res = await fetch(apiUrl + "?order_id=" + encodeURIComponent(orderIds.join(",")));
      if (!res.ok) {
        alert("Could not fetch label data.");
        return;
      }
      var payload = await res.json();

      if (payload.already_generated && payload.download_url) {
        var dlUrl = payload.download_url;
        var dlWin = window.open(dlUrl, "_blank");
        if (!dlWin) window.location.href = dlUrl;
        return;
      }

      var labels = payload.labels || [];
      var settings = Object.assign({}, payload.settings || {});
      // HSN debug logging (temporary):
      // try {
      //   var hsnDebug = labels.slice(0, 5).map(function (l) {
      //     var firstProduct = Array.isArray(l.products) && l.products.length ? l.products[0] : {};
      //     return {
      //       order_number: l.order_number,
      //       awb: l.awb,
      //       product_count: Array.isArray(l.products) ? l.products.length : 0,
      //       hsn: firstProduct ? firstProduct.hsn : undefined,
      //       hsn_code: firstProduct ? firstProduct.hsn_code : undefined,
      //     };
      //   });
      //   console.log("[Label HSN Debug] sample labels:", hsnDebug);
      // } catch (e) {
      //   console.warn("[Label HSN Debug] failed to inspect labels", e);
      // }
      var atsProxyUrl = settings.ats_label_proxy_url || "";
      var bootSize =
        typeof window.SHIPZEE_LABEL_PAGE_SIZE === "string"
          ? window.SHIPZEE_LABEL_PAGE_SIZE.trim().toLowerCase()
          : "";
      if (bootSize) settings.label_page_size = bootSize;
      settings.label_page_size = normalizedLabelPageSize(settings);
      if (!labels.length) {
        alert("No valid labels found.");
        return;
      }

      var atsLabels = labels.filter(function (l) {
        return !!l.is_amazon;
      });
      var localLabels = labels.filter(function (l) {
        return !l.is_amazon;
      });

      if (!window.pdfMake) {
        alert("PDF generator library is not loaded.");
        return;
      }

      if (DEV) window.__labelPdfBarcodeMs = 0;

      if (localLabels.length) {
        await preloadLogosParallel(localLabels, settings);
      }

      var merged;
      if (!localLabels.length && atsLabels.length) {
        // ATS-only selection: do not generate Idiotship template labels.
        merged = await mergeAmazon(null, atsLabels, atsProxyUrl);
      } else {
        var pageCfg = pageConfig(settings.label_page_size);
        var bytes = await renderLabelsToPdfBytes(localLabels, settings, pageCfg);
        merged = await mergeAmazon(bytes, atsLabels, atsProxyUrl);
      }
      var blob = new Blob([merged], { type: "application/pdf" });
      triggerPdfBlobDownloadInCurrentTab(blob);

    } catch (e) {
      console.error("Label PDF generation failed", e);
      alert("Label PDF generation failed. Please try again or contact support.");
    } finally {
      hideLabelDownloadOverlay();
      timeEnd("label_pdf_total");
    }
  }

  window.generateLabelsFromOrderIds = generateLabelsFromOrderIds;

  window.ShipzeeLabelPdfCore = {
    quickHash: quickHash,
    splitProductChunks: splitProductChunks,
    prepareLabelProductRows: prepareLabelProductRows,
    pageConfig: pageConfig,
    text: text,
    LABELS_PER_PDF_CHUNK: LABELS_PER_PDF_CHUNK,
  };
})();

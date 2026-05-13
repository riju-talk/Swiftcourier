/**
 * Expose fetch response body as a data URL for pdfMake — no re-encoding or resizing.
 * maxW, maxH, quality are ignored (kept for a stable caller API).
 */
(function (global) {
  function blobToDataUrl(blob) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onloadend = function () {
        resolve(reader.result || "");
      };
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }

  /**
   * @param {Response} res - fetch Response (ok, image body)
   * @param {number} maxW - unused
   * @param {number} maxH - unused
   * @param {number} quality - unused
   * @returns {Promise<string>} data URL (original bytes)
   */
  async function optimizeFromResponse(res, maxW, maxH, quality) {
    var blob = await res.blob();
    return blobToDataUrl(blob);
  }

  global.ShipzeeImageOptimizer = {
    optimizeFromResponse: optimizeFromResponse,
    blobToDataUrl: blobToDataUrl,
  };
})(typeof window !== "undefined" ? window : this);

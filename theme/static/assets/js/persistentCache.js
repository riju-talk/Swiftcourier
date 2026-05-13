/**
 * Small localStorage-backed cache with in-memory fallback on quota / privacy errors.
 * Keys are prefixed to avoid collisions with other app data.
 */
(function (global) {
  var PREFIX = "shipzee_lc_";
  var memFallback = new Map();

  function fullKey(key) {
    return PREFIX + key;
  }

  function safeGet(key) {
    try {
      var v = localStorage.getItem(fullKey(key));
      if (v != null) return v;
    } catch (e) {}
    return memFallback.has(key) ? memFallback.get(key) : null;
  }

  function safeSet(key, value) {
    try {
      localStorage.setItem(fullKey(key), value);
      memFallback.delete(key);
      return true;
    } catch (e) {
      memFallback.set(key, value);
      return false;
    }
  }

  function safeRemove(key) {
    try {
      localStorage.removeItem(fullKey(key));
    } catch (e) {}
    memFallback.delete(key);
  }

  global.ShipzeePersistentCache = {
    get: function (key) {
      return safeGet(key);
    },
    set: function (key, value) {
      return safeSet(key, value);
    },
    remove: function (key) {
      safeRemove(key);
    },
    clearMemoryFallback: function () {
      memFallback.clear();
    },
  };
})(typeof window !== "undefined" ? window : this);

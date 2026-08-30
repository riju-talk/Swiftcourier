
// SwiftCourier uses a permanent, always-expanded vertical sidebar (see the
// Stitch redesign). VRISTO persists the menu mode in localStorage under
// "_x_menu"; Alpine's $persist plugin reads that key while the store is being
// created, which is AFTER "alpine:init" fires - so setting the store property in
// an alpine:init handler gets clobbered by the persisted value. We fix it at the
// source: overwrite the persisted key now (this script runs before the deferred
// alpine bundle), then also pin the store and neutralise toggleMenu so nothing
// can switch back to the collapsing icon-rail.
try {
    localStorage.setItem('_x_menu', JSON.stringify('vertical'));
} catch (e) { /* private mode / storage disabled - the alpine:init pin still runs */ }

document.addEventListener('alpine:init', () => {
    const appStore = Alpine.store('app');
    appStore.menu = 'vertical';
    appStore.toggleMenu = function () {
        this.menu = 'vertical';
    };
});

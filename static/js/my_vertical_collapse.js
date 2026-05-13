
// 1) When Alpine initializes, force the store’s menu to "collapsible-vertical"
//    and override toggleMenu() so it can never switch away.
document.addEventListener('alpine:init', () => {
    const appStore = Alpine.store('app');

    // Immediately set it, in case anything else tries to read it later:
    appStore.menu = 'collapsible-vertical';

    // Override toggleMenu so it always re-assigns "collapsible-vertical":
    appStore.toggleMenu = function (_val) {
        this.menu = 'collapsible-vertical';
    };
});

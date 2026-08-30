/**
 * This is a minimal config.
 *
 * If you need the full config, get it from here:
 * https://unpkg.com/browse/tailwindcss@latest/stubs/defaultConfig.stub.js
 */
const plugin = require('tailwindcss/plugin');
const rotateX = plugin(function ({ addUtilities }) {
    addUtilities({
        '.rotate-y-180': {
            transform: 'rotateY(180deg)',
        },
    });
});
module.exports = {
    // Tailwind v4 ignores `content` (this file is only loaded via the
    // `@config` directive in src/styles.css for theme/plugins). Content
    // globs now live as `@source` directives in src/styles.css instead.
    content: [],

    // safelist: [
    //     'bg-red-50', 'hover:bg-red-100', 'text-red-600', 'focus:ring-red-200',
    //     'bg-green-600', 'hover:bg-green-700', 'focus:ring-green-300',
    //     'transform', 'hover:scale-105',
    //   ],
    darkMode: 'class',
    theme: {
        container: {
            center: true,
        },
        extend: {
            transitionProperty: {
                'colors': 'background-color, border-color, color, fill, stroke'
            },
            colors: {
                // Brand: red/black/white "enterprise" system, matched to the
                // sign-in page (account/templates/account/signin.dj). `primary`
                // is the single red accent used for links, active nav, focus
                // rings and primary buttons across every dashboard.
                primary: {
                    DEFAULT: '#dc2626', // red-600
                    light: '#fef2f2', // red-50
                    'dark-light': 'rgba(220,38,38,.15)',
                },
                secondary: {
                    DEFAULT: '#111827', // near-black (was purple) - used for
                    light: '#f3f4f6', // secondary buttons / neutral emphasis
                    'dark-light': 'rgb(17 24 39 / 15%)',
                },
                success: {
                    DEFAULT: '#00ab55',
                    light: '#ddf5f0',
                    'dark-light': 'rgba(0,171,85,.15)',
                },
                danger: {
                    DEFAULT: '#e7515a',
                    light: '#fff5f5',
                    'dark-light': 'rgba(231,81,90,.15)',
                },
                warning: {
                    DEFAULT: '#e2a03f',
                    light: '#fff9ed',
                    'dark-light': 'rgba(226,160,63,.15)',
                },
                info: {
                    DEFAULT: '#2196f3',
                    light: '#e7f7ff',
                    'dark-light': 'rgba(33,150,243,.15)',
                },
                dark: {
                    DEFAULT: '#3b3f5c',
                    light: '#eaeaec',
                    'dark-light': 'rgba(59,63,92,.15)',
                },
                black: {
                    DEFAULT: '#0e1726',
                    light: '#e3e4eb',
                    'dark-light': 'rgba(14,23,38,.15)',
                },
                white: {
                    DEFAULT: '#ffffff',
                    light: '#e0e6ed',
                    dark: '#888ea8',
                },
            },
            fontFamily: {
                nunito: ['"Plus Jakarta Sans"', 'Nunito', 'ui-sans-serif', 'system-ui', 'sans-serif'],
                display: ['"Plus Jakarta Sans"', 'ui-sans-serif', 'sans-serif'],
            },
            spacing: {
                4.5: '18px',
            },
            boxShadow: {
                '3xl': '0 2px 2px rgb(224 230 237 / 46%), 1px 6px 7px rgb(224 230 237 / 46%)',
            },
            typography: {
                DEFAULT: {
                    css: {
                        h1: { fontSize: '40px' },
                        h2: { fontSize: '32px' },
                        h3: { fontSize: '28px' },
                        h4: { fontSize: '24px' },
                        h5: { fontSize: '20px' },
                        h6: { fontSize: '16px' },
                    },
                },
            },
        },
    },
    plugins: [
        /**
         * '@tailwindcss/forms' is the forms plugin that provides a minimal styling
         * for forms. If you don't like it or have own styling for forms,
         * comment the line below to disable '@tailwindcss/forms'.
         */
        require('@tailwindcss/forms'),
        require('@tailwindcss/typography'),
        rotateX,
    ],
};

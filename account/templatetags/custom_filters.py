from django import template

register = template.Library()

@register.filter
def get_courier_icon(courier):
    icons = {
        'xpressbees': 'fas fa-shipping-fast',
        'delhivery': 'fas fa-truck',
        'ecomexpress': 'fas fa-boxes-packing',
        'shadowfax': 'fas fa-bolt',
        'bluedart': 'fas fa-plane',
    }
    return icons.get(courier, 'fas fa-shipping-fast')

@register.filter
def get_courier_bg(courier):
    bg_classes = {
        'xpressbees': 'bg-blue-100 dark:bg-blue-900',
        'delhivery': 'bg-green-100 dark:bg-green-900',
        'ecomexpress': 'bg-purple-100 dark:bg-purple-900',
        'shadowfax': 'bg-amber-100 dark:bg-amber-900',
        'bluedart': 'bg-indigo-100 dark:bg-indigo-900',
    }
    return bg_classes.get(courier, 'bg-blue-100 dark:bg-blue-900')
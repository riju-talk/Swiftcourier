import importlib


def get_courier_handler(courier):
    """Dynamically import and return the courier handler module."""
    module = importlib.import_module(courier.integration_path)
    return module

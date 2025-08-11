import importlib
import config
from exchanges.base import Exchange

def get_configured_exchanges() -> dict[str, Exchange]:
    """
    Reads the config, imports the necessary exchange modules,
    and returns a dictionary of instantiated exchange clients.
    """
    exchange_clients = {}
    for name, settings in config.EXCHANGES.items():
        # `settings` is the dictionary for the exchange, e.g., {'API_CONFIG': {...}}
        api_config = settings.get('API_CONFIG')

        # If the API_CONFIG dictionary exists and is not None, proceed.
        if api_config:
            try:
                module_name = f"exchanges.{name}"
                class_name = f"{name.capitalize()}Exchange"

                exchange_module = importlib.import_module(module_name)
                exchange_class = getattr(exchange_module, class_name)

                # Pass the entire config dictionary to the class constructor
                client_instance = exchange_class(api_config=api_config)
                exchange_clients[name] = client_instance
                print(f"+ Successfully initialized {client_instance}")

            except (ImportError, AttributeError):
                print(f"! Warning: Could not find or load module for '{name}'. Check file and class names.")
            except Exception as e:
                print(f"! Error initializing {name}: {e}")
        else:
            # This will be printed if 'API_CONFIG' is missing or None
            print(f"- Skipping {name}: Not configured.")

    if not exchange_clients:
        print("\nNo exchanges were configured. Please add API keys to config.py and try again.")

    return exchange_clients
